const usernameInput = document.querySelector('#username')
const emailInput = document.querySelector('#email')

usernameInput.addEventListener('keyup', (e) => {
    const username = e.target.value;

    // 重置
    e.target.classList.remove('is-invalid');
    e.target.nextElementSibling.innerText = '';

    fetch('/authentication/validate_username/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ "username": username }),
    })
        .then((res) => res.json()) // 如果后端返回的是json数据
        .then((data) => {
            if (data.status == 'error') {
                e.target.classList.add('is-invalid');
                e.target.nextElementSibling.innerText = data.msg;
            } else {
                e.target.classList.remove('is-valid');
            }
        })
})



emailInput.addEventListener('keyup', (e) => {
    const email = e.target.value;

    // 重置
    e.target.classList.remove('is-invalid');
    e.target.nextElementSibling.innerText = '';

    fetch('/authentication/validate_email/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ "email": email }),
    })
        .then((res) => res.json())
        .then((data) => {
            if (data.status == 'error') {
                e.target.classList.add('is-invalid');
                e.target.nextElementSibling.innerText = data.msg;
            } else {
                e.target.classList.remove('is-valid');
            }
        })
})