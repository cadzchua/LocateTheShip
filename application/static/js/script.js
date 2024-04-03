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
    var form = document.getElementById("filterForm");
    form.classList.toggle("minimized");
}

window.onload = function() {
    var savedFormData = localStorage.getItem("formData");
    if (savedFormData) {
        var formData = JSON.parse(savedFormData);
        document.getElementById("shipName").value = formData.shipName;
        document.getElementById("mmsi").value = formData.mmsi;
        document.getElementById("datetime1").value = formData.datetime1;
        document.getElementById("datetime2").value = formData.datetime2;
    }
};

document.getElementById("myButton").addEventListener("click", function() {
    var button = document.getElementById("myButton");
    if (button.textContent === "+") {
        button.textContent = "-";
    } else {
        button.textContent = "+";
    }
});