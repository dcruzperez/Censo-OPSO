"""Formularios del reparto de sectores (HU-06).

Se separan de forms.py por responsabilidad, igual que la app usuarios separó
forms.py (autenticación), forms_gestion.py (administración) y forms_permisos.py
(matriz): cada historia de usuario tiene su archivo, y así el código de una se
puede leer y revisar sin arrastrar el de las otras.
"""

from django import forms

from usuarios.models import RolCodigo, Usuario

from .models import AsignacionSector

CLASE_TEXTO = "form-control"
CLASE_SELECT = "form-select"


class CampoCensistas(forms.ModelMultipleChoiceField):
    """Selector de censistas que muestra el nombre y el correo de cada uno.

    Mismo recurso que CampoRol en la HU-03 y CampoComuna en la HU-05: al
    redefinir label_from_instance, cada casilla dice «Marta Soto ·
    censista@opso.cl» en vez de solo el nombre.

    Importa porque en un operativo grande puede haber dos personas con el mismo
    nombre, y asignar a la equivocada no produce ningún error: produce un censista
    que se presenta en el sector de otro. El correo desambigua.
    """

    def label_from_instance(self, obj):
        nombre = obj.get_full_name() or obj.email
        return f"{nombre} · {obj.email}"


class AsignarSectorForm(forms.Form):
    """Define QUIÉNES cubren un sector. Se envía el conjunto completo.

    ----------------------------------------------------------------------
    ¿POR QUÉ UN CONJUNTO Y NO "AGREGAR UNA PERSONA A LA VEZ"?
    ----------------------------------------------------------------------
    Porque la pregunta que resuelve el supervisor no es "¿a quién agrego?" sino
    "¿quiénes cubren este sector?". Con casillas de verificación esa pregunta se
    responde de un vistazo y la respuesta se corrige en un clic: se marca a quien
    entra y se desmarca a quien sale, y una REASIGNACIÓN —que es las dos cosas a
    la vez— es una sola operación en vez de dos.

    Es exactamente el mismo enfoque que PermisosRolForm en la HU-04, y por la
    misma razón. También comparte su consecuencia: guardar es CALCULAR LA
    DIFERENCIA entre lo que había y lo que llegó, no insertar sin más.

    ----------------------------------------------------------------------
    QUIÉNES APARECEN EN LA LISTA
    ----------------------------------------------------------------------
    Solo cuentas con rol CENSISTA y habilitadas. Las dos condiciones importan y
    son distintas:

      - El ROL, porque asignar terreno a un supervisor o a un administrador
        confundiría la separación de funciones que la HU-03 estableció: quien
        valida el trabajo no debe ser quien lo levanta, o el control cruzado
        desaparece.
      - El ESTADO, porque una cuenta deshabilitada no puede iniciar sesión (HU-03),
        así que asignarle un sector sería mandar a trabajar a alguien que no puede
        entrar al sistema. El sector parecería cubierto y no lo estaría, que es
        justo el error que esta historia existe para evitar.
    """

    censistas = CampoCensistas(
        label="Censistas a cargo del sector",
        queryset=Usuario.objects.none(),  # se ajusta en __init__
        required=False,  # dejar el sector sin nadie es una decisión válida
        widget=forms.CheckboxSelectMultiple,
        help_text=(
            "Marca a quienes deben cubrir este sector. Al guardar, quien quede "
            "desmarcado pierde la asignación (el historial se conserva)."
        ),
    )
    observaciones = forms.CharField(
        label="Observaciones para el equipo",
        required=False,
        max_length=300,
        widget=forms.Textarea(
            attrs={
                "class": CLASE_TEXTO,
                "rows": 2,
                "placeholder": "Ej.: empezar por el pasaje sur, la subida está en obras.",
            }
        ),
        help_text=(
            "Se guarda en las asignaciones NUEVAS de este guardado. Las que ya "
            "existían conservan sus propias observaciones."
        ),
    )

    def __init__(self, *args, sector, asignado_por=None, **kwargs):
        """sector es obligatorio y va por nombre.

        Se exige como argumento de palabra clave (después de *) para que ninguna
        llamada pueda pasarlo por posición y confundirlo con `data`. Sin sector el
        formulario no sabe qué estado inicial mostrar ni sobre qué guardar.
        """
        self.sector = sector
        self.asignado_por = asignado_por
        super().__init__(*args, **kwargs)

        self.fields["censistas"].queryset = self.censistas_disponibles()

        # Estado inicial: quienes YA tienen el sector.
        #
        # Solo se fija cuando NO llegaron datos. Si el formulario se está
        # reenviando tras un error, el valor inicial no debe pisar lo que el
        # supervisor había marcado; Django ya conserva los datos enviados. Es el
        # mismo cuidado que PermisosRolForm documentó en la HU-04.
        if not self.is_bound:
            self.fields["censistas"].initial = list(
                sector.asignaciones.filter(activa=True).values_list(
                    "censista_id", flat=True
                )
            )

    def censistas_disponibles(self):
        """Censistas habilitados, más los que ya estén asignados a este sector.

        La segunda parte es el caso borde que sin cuidado rompe la pantalla: si a
        un censista se le asignó un sector y después se deshabilitó su cuenta, no
        aparecería en la lista, saldría desmarcado, y al guardar CUALQUIER otro
        cambio quedaría desasignado sin que el supervisor lo pidiera ni lo viera.

        Incluyéndolo se hace visible el problema —aparece marcado y la plantilla lo
        señala— y la decisión de retirarlo queda donde corresponde: en las manos de
        quien mira la pantalla.
        """
        from django.db.models import Q

        return (
            Usuario.objects.filter(
                Q(rol__codigo=RolCodigo.CENSISTA, is_active=True)
                | Q(asignaciones_sector__sector=self.sector,
                    asignaciones_sector__activa=True)
            )
            .distinct()
            .select_related("rol")
            .order_by("first_name", "last_name")
        )

    def censistas_seleccionados(self):
        """Los censistas marcados: los enviados si hay POST, los de la base si no.

        Existe para que la plantilla y guardar() pregunten lo mismo a la misma
        fuente. Sin este método, la plantilla leería la base de datos y el
        guardado los datos enviados, y tras un error de validación la pantalla
        mostraría un estado distinto del que se va a guardar.
        """
        if self.is_bound and self.is_valid():
            return list(self.cleaned_data["censistas"])

        return list(self.sector.censistas_asignados())

    def guardar(self):
        """Aplica el conjunto enviado y devuelve (antes, despues).

        Devuelve las dos listas de Usuario para que la vista arme el detalle de la
        bitácora con describir_cambio_asignaciones(). La comparación se hace AQUÍ,
        con el estado leído justo antes de escribir, y no en la vista: así el
        "antes" que se audita es el que realmente había en la base de datos.

        Tres movimientos posibles, y solo se ejecutan los necesarios:

          entra y no estaba nunca -> se crea una fila nueva
          entra y estuvo antes    -> se REACTIVA su fila histórica
          sale                    -> se desactiva su fila (se conserva)

        El caso del medio es el que justifica el índice único parcial del modelo:
        reactivar en vez de crear evita acumular una fila por cada ida y vuelta, y
        mantiene un solo registro por persona y sector con su fecha original.
        """
        activas_antes = list(
            self.sector.asignaciones.filter(activa=True).select_related("censista")
        )
        antes = [asignacion.censista for asignacion in activas_antes]
        despues = list(self.cleaned_data["censistas"])

        ids_antes = {usuario.pk for usuario in antes}
        ids_despues = {usuario.pk for usuario in despues}

        # 1. Quien sale: se desactiva conservando la fila.
        for asignacion in activas_antes:
            if asignacion.censista_id not in ids_despues:
                asignacion.desactivar()

        # 2. Quien entra.
        observaciones = self.cleaned_data.get("observaciones", "")
        for censista in despues:
            if censista.pk in ids_antes:
                continue  # ya la tenía: no se toca ni su fecha ni sus observaciones

            historica = self.sector.asignaciones.filter(
                censista=censista, activa=False
            ).first()

            if historica is not None:
                historica.activa = True
                historica.desasignado_en = None
                historica.asignado_por = self.asignado_por
                if observaciones:
                    historica.observaciones = observaciones
                historica.save(
                    update_fields=[
                        "activa",
                        "desasignado_en",
                        "asignado_por",
                        "observaciones",
                    ]
                )
            else:
                AsignacionSector.objects.create(
                    sector=self.sector,
                    censista=censista,
                    asignado_por=self.asignado_por,
                    observaciones=observaciones,
                )

        return antes, despues


class FiltroAsignacionesForm(forms.Form):
    """Filtros del panel de reparto de un operativo.

    Form y no ModelForm: no crea ni modifica nada, solo limpia lo que llega por la
    URL. Mismo razonamiento que los filtros de la HU-03 y la HU-05.
    """

    COBERTURA = (
        ("", "Todos los sectores"),
        ("sin_asignar", "Solo los que no tienen a nadie"),
        ("asignados", "Solo los que ya tienen equipo"),
    )

    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": CLASE_TEXTO,
                "placeholder": "Sector o comuna",
                "autocomplete": "off",
            }
        ),
    )
    cobertura = forms.ChoiceField(
        label="Cobertura",
        required=False,
        choices=COBERTURA,
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )
    censista = forms.ModelChoiceField(
        label="Censista",
        required=False,
        queryset=Usuario.objects.none(),  # se ajusta en __init__
        empty_label="Cualquier censista",
        widget=forms.Select(attrs={"class": CLASE_SELECT}),
    )

    def __init__(self, *args, operativo=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Solo los censistas DESPLEGADOS EN ESTE OPERATIVO, no todos los del
        # sistema: filtrar por alguien que no trabaja aquí devolvería siempre una
        # lista vacía, y una opción que nunca da resultados es una opción que
        # estorba.
        if operativo is not None:
            self.fields["censista"].queryset = operativo.censistas_desplegados()

    def clean_q(self):
        return (self.cleaned_data.get("q") or "").strip()
