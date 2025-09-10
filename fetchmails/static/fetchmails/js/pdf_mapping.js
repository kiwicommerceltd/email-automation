// document.addEventListener('DOMContentLoaded', function () {
//   const uploadInput = document.getElementById('pdfUpload');
//   const previewContainer = document.getElementById('pdfPreview');
//   const mappingContainer = document.getElementById('mappingResult');

//   const csvKeys = [
//     "description", "product_code", "price", "price_per_unit", "quantity", "order_quantity"
//   ];

//   uploadInput.addEventListener('change', function () {
//     const file = uploadInput.files[0];
//     if (!file) return;

//     const formData = new FormData();
//     formData.append('pdf_file', file);

//     fetch('/fetchmails/ajax/extract-pdf-keys/', {
//       method: 'POST',
//       body: formData,
//       headers: {
//         'X-CSRFToken': getCSRFToken()
//       }
//     })
//     .then(response => response.json())
//     .then(data => {
//       // Show PDF Preview
//       const fileURL = URL.createObjectURL(file);
//       previewContainer.innerHTML = `<embed src="${fileURL}" width="100%" height="400px" type="application/pdf"/>`;

//       // Generate key mapping UI
//       mappingContainer.innerHTML = '';
//       if (data.keys && data.keys.length > 0) {
//         data.keys.forEach(key => {
//           const select = document.createElement('select');
//           select.name = `mapping_${key}`;
//           select.classList.add('form-control', 'mapping-dropdown');
//           select.dataset.originalKey = key;

//           const defaultOption = document.createElement('option');
//           defaultOption.value = "";
//           defaultOption.textContent = "-- Select CSV Key --";
//           select.appendChild(defaultOption);

//           csvKeys.forEach(csvKey => {
//             const option = document.createElement('option');
//             option.value = csvKey;
//             option.textContent = csvKey;
//             select.appendChild(option);
//           });

//           const label = document.createElement('label');
//           label.textContent = ` "${key}" :`;
//           label.style.display = 'flex';
//           label.style.gap = '15px';
//           label.style.maxWidth = 'unset'; 
//           label.style.minWidth = 'unset'; 
//           label.style.width = '35%'; 
//           label.style.fontSize = '15px'; 
//           label.style.justifyContent = 'space-between';
//           label.appendChild(select);

//           mappingContainer.appendChild(label);
//           mappingContainer.appendChild(document.createElement('br'));
//         });

//         // Add Save button
//         const saveBtn = document.createElement('button');
//         saveBtn.textContent = 'Save Mapping';
//         saveBtn.id = 'mapping-save-btn';
//         saveBtn.type = 'button';
//         saveBtn.style.Padding = '10px 15px'
//         saveBtn.classList.add('btn', 'btn-success', 'mt-3');
//         mappingContainer.appendChild(saveBtn);

//         // Bind save button click
//         saveBtn.addEventListener('click', (e) => {
//           // e.preventDefault();  // ✅ Prevent default form submission
//           const mappedData = {};
//           const selects = document.querySelectorAll('select.mapping-dropdown');
//           selects.forEach(select => {
//             const originalKey = select.dataset.originalKey;
//             const selectedValue = select.value.trim();
          
//             if (selectedValue !== "") {
//               mappedData[originalKey] = selectedValue;
//             }
//           });

//           const customerId = document.getElementById('id_customer_id').value;
//           console.log("Sending mapping to /fetchmails/save-mapping/");
//           fetch('/fetchmails/save-mapping/', {
//             method: 'POST',
//             headers: {
//               'Content-Type': 'application/json',
//               'X-CSRFToken': getCSRFToken()
//             },
//             body: JSON.stringify({
//               customer_id: customerId,
//               mapping: mappedData
//             })
//           })
//           .then(res => res.json())
//           .then(data => {
//             if (data.success) {
//               console.log("✅ Mapping saved successfully!");
//             } else {
//               alert("❌ Failed to save mapping.");
//             }
//           });
//         });
//       }
//     })
//     .catch(err => {
//       console.error('Upload failed', err);
//     });
//   });

//   function getCSRFToken() {
//     return document.querySelector('[name=csrfmiddlewaretoken]').value;
//   }
// });
