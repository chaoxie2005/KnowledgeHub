const eyeImg = document.querySelector('#hide-password')
const pwdInput = document.querySelector('#password')

eyeImg.addEventListener('click', (e) => {
    let type = pwdInput.getAttribute('type')
    if (type == 'password') {
        pwdInput.setAttribute('type', 'text');
        eyeImg.setAttribute('src', '/static/img/authentication/eye.svg');
    } else {
        pwdInput.setAttribute('type', 'password');
        eyeImg.setAttribute('src', '/static/img/authentication/eye_off.svg');
    }
})