"""Formulario de la matriz de permisos (HU-04).

Se separa de forms_gestion.py por el mismo criterio con que views_gestion.py se
separó de views.py: un archivo por historia de usuario mientras el archivo tenga
un tamaño razonable. Así el código de cada historia se puede leer, revisar y
defender de forma independiente.

DECISIÓN DE DISEÑO — un formulario POR ROL, no uno gigante para toda la matriz.

La pantalla muestra una tabla de permisos (filas) por roles (columnas). Se
evaluaron dos formas de modelarla:

  A) UN formulario con un campo booleano por cada celda. Con 19 permisos y 3
     roles serían 57 campos generados dinámicamente en __init__, con nombres
     construidos a mano del tipo "permiso_7_rol_2". Habría que parsear esos
     nombres al guardar para saber a qué celda corresponde cada uno.

  B) UN formulario por rol, cada uno con un único campo de selección múltiple
     (ModelMultipleChoiceField). Django resuelve solo la validación de que los
     identificadores enviados existan y sean permisos válidos, y "los permisos
     de este rol" queda expresado como lo que es: una lista.

Se eligió B. La validación la hace Django, no código propio, y el formulario se
puede probar aislado ("dale estos permisos al rol Supervisor") sin construir la
matriz completa. Los formularios se distinguen entre sí con un PREFIJO, que es
el mecanismo estándar de Django para tener varios formularios en una misma
página sin que sus campos choquen.
"""

from django import forms

from .models import Permiso


class PermisosRolForm(forms.Form):
    """Los permisos concedidos a UN rol.

    Se instancia una vez por cada rol editable de la matriz. El prefijo hace que
    el campo se llame "rol2-permisos" en el HTML, de modo que los formularios de
    Supervisor y Censista no se pisen al enviarse en el mismo POST.
    """

    permisos = forms.ModelMultipleChoiceField(
        # El queryset real se fija en __init__. Se declara vacío y no
        # Permiso.objects.all() porque un queryset evaluado en la definición de
        # la clase se resolvería UNA vez al importar el módulo y quedaría
        # obsoleto: un permiso agregado después no aparecería hasta reiniciar el
        # servidor.
        queryset=Permiso.objects.none(),
        required=False,  # un rol sin ningún permiso es un estado válido
        widget=forms.CheckboxSelectMultiple,
        label="Permisos concedidos",
    )

    def __init__(self, *args, rol, permisos_disponibles=None, **kwargs):
        """
        Parámetros:
            rol                  -> el Rol al que pertenece este formulario.
            permisos_disponibles -> queryset de permisos que se pueden conceder.
                                    Se recibe desde fuera para que la vista lo
                                    consulte UNA vez y lo reparta entre los
                                    formularios, en vez de una consulta por rol.
        """
        self.rol = rol
        # El prefijo se calcula a partir del rol, nunca se pasa a mano: así es
        # imposible que la plantilla y el formulario usen nombres distintos.
        kwargs.setdefault("prefix", self.prefijo_de(rol))
        super().__init__(*args, **kwargs)

        if permisos_disponibles is None:
            permisos_disponibles = Permiso.objects.filter(activo=True)
        self.fields["permisos"].queryset = permisos_disponibles

        # Estado inicial: lo que el rol tiene concedido hoy. Solo para el
        # formulario sin datos (GET); en un POST manda lo que envió el navegador.
        if not self.is_bound:
            self.initial["permisos"] = list(
                rol.permisos.values_list("pk", flat=True)
            )

    @staticmethod
    def prefijo_de(rol):
        """Prefijo HTML de los campos de este rol. Ej.: "rol2"."""
        return f"rol{rol.pk}"

    @property
    def nombre_campo_html(self):
        """Nombre del atributo name= de las casillas. Ej.: "rol2-permisos".

        La plantilla dibuja la matriz celda por celda con HTML propio (una tabla
        con las casillas repartidas en columnas), en vez de usar {{ form.permisos }},
        que produciría una lista vertical inservible como matriz. Este método es
        el puente: garantiza que el name= que escribe la plantilla es exactamente
        el que el formulario espera al validar.
        """
        return self.add_prefix("permisos")

    def pks_seleccionados(self):
        """Identificadores marcados, vengan del POST o de la base de datos.

        La plantilla lo usa para decidir qué casillas dibuja marcadas. Al
        reenviar un formulario con errores hay que mostrar lo que la persona
        había marcado, no lo que dice la base de datos, o perdería su trabajo.

        Se acepta que self.data sea un QueryDict (lo que llega en una petición
        real, con getlist para los campos repetidos) o un dict corriente (como se
        construye en las pruebas unitarias). Un formulario que solo funciona
        dentro de una petición HTTP no se puede probar aislado, que es
        precisamente lo que se buscaba al separarlo de la vista.
        """
        if not self.is_bound:
            return set(self.initial.get("permisos") or [])

        nombre = self.nombre_campo_html
        if hasattr(self.data, "getlist"):
            crudos = self.data.getlist(nombre)
        else:
            crudos = self.data.get(nombre, [])
            # Un dict puede traer un único valor sin envolver en lista.
            if isinstance(crudos, (str, int)):
                crudos = [crudos]

        return {int(valor) for valor in crudos if str(valor).isdigit()}

    def guardar(self):
        """Aplica los permisos marcados al rol y devuelve (antes, despues).

        Devuelve las dos listas de objetos Permiso para que la vista pueda
        describir el cambio en la auditoría. El formulario no escribe en la
        bitácora: no conoce al administrador ni la petición, y mezclar ambas
        responsabilidades haría imposible probarlo por separado.

        DETALLE IMPORTANTE — los permisos desactivados se conservan.

        La matriz solo muestra los permisos con activo=True. Si un permiso se
        desactivó pero seguía concedido a este rol, no aparece como casilla y
        por tanto no viene en el POST. Un set() con solo lo marcado lo BORRARÍA
        en silencio, y al reactivar el permiso el rol lo habría perdido sin que
        nadie lo decidiera. Se añaden explícitamente para que guardar la matriz
        nunca revoque algo que la matriz no mostraba.
        """
        antes = list(self.rol.permisos.all())

        seleccionados = list(self.cleaned_data["permisos"])
        concedidos_no_visibles = list(self.rol.permisos.filter(activo=False))

        self.rol.permisos.set(seleccionados + concedidos_no_visibles)

        despues = list(self.rol.permisos.all())
        return antes, despues
