$(document).ready(function() {
    $('#loginForm').on('submit', function(e) {
        e.preventDefault();
        
        let isValid = true;
        const username = $('#username').val().trim();
        const password = $('#password').val().trim();
        
        // Validación de correo electrónico
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        
        if (username === '' || !emailRegex.test(username)) {
            $('#username').addClass('is-invalid');
            isValid = false;
        } else {
            $('#username').removeClass('is-invalid');
        }
        
        if (password === '') {
            $('#password').addClass('is-invalid');
            isValid = false;
        } else {
            $('#password').removeClass('is-invalid');
        }
        
        if (isValid) {
            const btn = $('.btn-login');
            const originalText = btn.text();
            btn.text('Procesando...').prop('disabled', true);
            
            setTimeout(() => {
                window.location.href = 'dashboard.html';
            }, 800);
        }
    });

    $('#password').on('input', function() {
        if($(this).val().trim() !== '') {
            $(this).removeClass('is-invalid');
        }
    });

    $('#username').on('input', function() {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if(emailRegex.test($(this).val().trim())) {
            $(this).removeClass('is-invalid');
        }
    });
});
