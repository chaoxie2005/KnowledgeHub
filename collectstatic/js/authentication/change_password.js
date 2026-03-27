// 获取所有密码输入框和眼睛图标
const passwordInput1 = document.getElementById('password_1'); // 旧密码
const passwordInput2 = document.getElementById('password_2'); // 新密码
const passwordInput3 = document.getElementById('password_3'); // 确认密码

const eyeIcon1 = document.getElementById('hide-password_1');
const eyeIcon2 = document.getElementById('hide-password_2');
const eyeIcon3 = document.getElementById('hide-password_3');

// 切换密码显示/隐藏的通用函数
function togglePassword(input, icon) {
    if (input.type === 'password') {
        input.setAttribute('type', 'text');
        icon.setAttribute('src', '/static/img/authentication/eye_off.svg')
    } else {
        input.setAttribute('type', 'password');
        icon.setAttribute('src', '/static/img/authentication/eye.svg')
    }
}

// 绑定点击事件
eyeIcon1.addEventListener('click', () => togglePassword(passwordInput1, eyeIcon1));
eyeIcon2.addEventListener('click', () => togglePassword(passwordInput2, eyeIcon2));
eyeIcon3.addEventListener('click', () => togglePassword(passwordInput3, eyeIcon3));