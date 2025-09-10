document.addEventListener('DOMContentLoaded', function () {
    const uploadInput = document.getElementById('pdfUpload');
    const previewContainer = document.getElementById('pdfPreview');
    const mappingContainer = document.getElementById('mappingResult');
  
    const csvKeys = [
      "description", "product_code", "price", "price_per_unit", "quantity", "order_quantity"
    ];
  
    uploadInput.addEventListener('change', function () {
      const file = uploadInput.files[0];
      if (!file) return;
  
      const formData = new FormData();
      formData.append('pdf_file', file);
  
      fetch('/fetchmails/ajax/extract-pdf-keys/', {
        method: 'POST',
        body: formData,
        headers: {
          'X-CSRFToken': getCSRFToken()
        }
      })
      .then(response => response.json())
      .then(data => {
        // Show PDF Preview
        const fileURL = URL.createObjectURL(file);
        previewContainer.innerHTML = `<embed src="${fileURL}" width="100%" height="400px" type="application/pdf"/>`;
  
        // Generate key mapping UI
        mappingContainer.innerHTML = '';
        if (data.keys && data.keys.length > 0) {
          data.keys.forEach(key => {
            const select = document.createElement('select');
            select.name = `mapping_${key}`;
            select.classList.add('form-control');
  
            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "-- Select CSV Key --";
            select.appendChild(defaultOption);
  
            csvKeys.forEach(csvKey => {
              const option = document.createElement('option');
              option.value = csvKey;
              option.textContent = csvKey;
              select.appendChild(option);
            });
  
            const label = document.createElement('label');
            label.textContent = `Map "${key}" to:`;
            label.appendChild(select);
  
            mappingContainer.appendChild(label);
            mappingContainer.appendChild(document.createElement('br'));
          });
        }
      })
      .catch(err => {
        console.error('Upload failed', err);
      });
    });
  
    function getCSRFToken() {
      return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
  });
  