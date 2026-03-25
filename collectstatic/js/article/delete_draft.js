const deleteBtnList = document.getElementsByClassName('deleteBtn')

for (let index = 0; index < deleteBtnList.length; index++) {
    deleteBtnList[index].addEventListener('click', confirmDelete);
}

function confirmDelete(e) {
    let draftId = e.target.getAttribute('draftID')
    Swal.fire({
        title: "你确定要删除吗?",
        text: "删除后将无法恢复!",
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#3085d6",
        cancelButtonColor: "#d33",
        confirmButtonText: "删除!",
        cancelButtonText: "取消"
    }).then((result) => {
        if (result.isConfirmed) {
            handleDelete(draftId)
        }
    })
}

function handleDelete(id) {
    fetch(`/article/delete_draft/${id}`).then((data) => {
        location.reload()
    })
}