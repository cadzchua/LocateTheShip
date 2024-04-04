function saveFormData() {
    var formData = {
        shipName: document.getElementById("shipName").value,
        mmsi: document.getElementById("mmsi").value,
        datetime1: document.getElementById("datetime1").value,
        datetime2: document.getElementById("datetime2").value
    };
    localStorage.setItem("formData", JSON.stringify(formData));
}

function clearFormData() {
    localStorage.removeItem("formData");
    location.reload(); 
}

function toggleForm() {
    var form = document.querySelector('.filter-form');
    var formContainer = document.querySelector('.filter-forms');
    var button = document.getElementById('myButton2');
    
    form.classList.toggle('minimized');
    formContainer.classList.toggle('expanded');
    
    if (form.classList.contains('minimized')) {
        button.textContent = '+';
        formContainer.style.backgroundColor = '#ffffff67'; 
    } else {
        button.textContent = '-';
        formContainer.style.backgroundColor = '#ffffff'; 
    }
}

window.onload = function() {
    var savedFormData = localStorage.getItem("formData");
    if (savedFormData) {
        var formData = JSON.parse(savedFormData);
        if (formData.shipName) {
            document.getElementById("shipName").value = formData.shipName;
            document.querySelector('.labelline1').style.transform = 'translate(-5px, -30px) scale(0.88)';
            document.querySelector('.labelline1').style.color = '#1372de';
            document.querySelector('.labelline1').style.fontWeight = 'bold';
            document.querySelector('.labelline1').style.backgroundColor = 'rgb(255, 255, 255)';
            document.querySelector('.labelline1').style.zIndex = '1112';
        }
        if (formData.mmsi) {
            document.getElementById("mmsi").value = formData.mmsi;
            document.querySelector('.labelline2').style.transform = 'translate(-5px, -30px) scale(0.88)';
            document.querySelector('.labelline2').style.color = '#1372de';
            document.querySelector('.labelline2').style.fontWeight = 'bold';
            document.querySelector('.labelline2').style.backgroundColor = 'rgb(255, 255, 255)';
            document.querySelector('.labelline2').style.zIndex = '1112';
        }
        document.getElementById("datetime1").value = formData.datetime1;
        document.getElementById("datetime2").value = formData.datetime2;
    }
};

document.getElementById("myButton").addEventListener("click", function() {
    window.location.href = "/";
});