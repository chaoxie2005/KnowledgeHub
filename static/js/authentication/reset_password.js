const eyeImg = document.querySelector('#hide-password_1')
const re_eyeImg = document.querySelector('#hide-password_2')
const passwordInput = document.querySelector('#password')
const re_passwordInput = document.querySelector('#re_password')

eyeImg.addEventListener('click', (e) => {
    let type = passwordInput.getAttribute('type')

    if (type == 'password') {
        passwordInput.setAttribute('type', 'text');
        eyeImg.setAttribute('src', '/static/img/authentication/eye_off.svg')
    } else {
        passwordInput.setAttribute('type', 'password');
        eyeImg.setAttribute('src', '/static/img/authentication/eye.svg')
    }
})

re_eyeImg.addEventListener('click', (e) => {
    let type = re_passwordInput.getAttribute('type')

    if (type == 'password') {
        re_passwordInput.setAttribute('type', 'text');
        re_eyeImg.setAttribute('src', '/static/img/authentication/eye_off.svg')
    } else {
        re_passwordInput.setAttribute('type', 'password');
        re_eyeImg.setAttribute('src', '/static/img/authentication/eye.svg')
    }
})
