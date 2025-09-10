document.addEventListener('DOMContentLoaded', function () {
  const options = window.CSV_KEYS || [];
  const fileInput = document.querySelector('#id_document');
  const previewDiv = document.querySelector('#existingPdfPreview');
  const extraDataField = document.querySelector('textarea[name="extra_data"]');

  const flexContainer = fileInput?.closest('.flex-container');
  const previewContainer = document.createElement('div');
  previewContainer.classList.add('file-preview-wrapper');

  if (flexContainer && flexContainer.parentNode) {
    flexContainer.parentNode.insertBefore(previewContainer, flexContainer.nextSibling);
  }

  function getPdfPathFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const encodedPath = params.get("saved_pdf_path");
    return encodedPath ? decodeURIComponent(encodedPath) : null;
  }

  const savedPdfPath = getPdfPathFromUrl();
  const fullPdfUrl = savedPdfPath ? `/media/${savedPdfPath}` : null;

  previewContainer.innerHTML = '';
  if (previewDiv) previewDiv.innerHTML = '';

  // ✅ PDF preview via URL
  if (fullPdfUrl && fullPdfUrl.endsWith(".pdf")) {
    fetch(fullPdfUrl)
      .then(res => {
        if (!res.ok) throw new Error("Failed to fetch PDF");
        return res.blob();
      })
      .then(() => {
        const pdfWithVersion = `${fullPdfUrl}?v=${Date.now()}`;
        previewContainer.innerHTML = `
          <embed src="${pdfWithVersion}" class="pdf-preview-embed" type="application/pdf" />
          <p><a href="${pdfWithVersion}" target="_blank">Download PDF</a></p>
        `;
        const prefillData = parseExtraData(extraDataField?.value);
        appendDynamicInputs(previewContainer, prefillData);
      })
      .catch(err => {
        console.error("PDF preview failed:", err);
        previewContainer.innerHTML = `<p style="color:red;">Could not preview saved PDF</p>`;
      });
  }

  // ✅ Existing preview fallback
  else if (previewDiv?.dataset?.pdfUrl) {
    const pdfUrl = previewDiv.dataset.pdfUrl;
    fetch(pdfUrl)
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch');
        return res.blob();
      })
      .then(() => {
        const pdfWithVersion = `${pdfUrl}?v=${Date.now()}`;
        previewDiv.innerHTML = `
          <div class="file-preview-wrapper" id="existingWrapper">
            <embed src="${pdfWithVersion}" class="pdf-preview-embed" type="application/pdf" />
            <p><a href="${pdfWithVersion}" target="_blank">Download PDF</a></p>
          </div>
        `;
        const wrapper = document.getElementById('existingWrapper');
        const prefillData = parseExtraData(extraDataField?.value);
        appendDynamicInputs(wrapper, prefillData);
      })
      .catch(err => {
        previewDiv.innerHTML = `<p style="color:red;">Could not load preview.</p>`;
        console.error('PDF preview error:', err);
      });
  }

  // ✅ Handle file input changes for PDF + Images
  fileInput?.addEventListener('change', function () {
    const file = fileInput.files[0];
    if (!file) return;

    previewDiv.innerHTML = '';
    previewContainer.innerHTML = '';

    const blobURL = URL.createObjectURL(file);
    let rendered = false;

    if (file.type === 'application/pdf') {
      const pdfDiv = document.createElement('div');
      pdfDiv.innerHTML = `<embed src="${blobURL}" class="pdf-preview-embed" type="application/pdf" />`;
      previewContainer.appendChild(pdfDiv);
      rendered = true;
    } else if (['image/png', 'image/jpeg', 'image/jpg'].includes(file.type)) {
      const img = document.createElement('img');
      img.src = blobURL;
      img.alt = 'Image Preview';
      img.style.maxWidth = '100%';
      img.style.maxHeight = '400px';
      previewContainer.appendChild(img);
      rendered = true;
    } else {
      previewContainer.innerHTML = `<p style="color:red;">Unsupported file type</p>`;
    }

    if (rendered && !document.getElementById('dynamicInputSection')) {
      const prefillData = parseExtraData(extraDataField?.value);
      appendDynamicInputs(previewContainer, prefillData);
    }
  });

  function parseExtraData(data) {
    if (!data) return {};
    try {
      return JSON.parse(data);
    } catch (e) {
      console.warn("Couldn't parse extra_data JSON", e);
      return {};
    }
  }

  function appendDynamicInputs(container, prefillData = {}) {
    const inputSection = document.createElement('div');
    inputSection.id = 'dynamicInputSection';
    inputSection.innerHTML = `
      <h4 style="padding-left: 0; margin-bottom: 10px; margin-top: 20px; font-weight: bold; font-size: 15px;">🗂️ Map Data Keys</h4>
    `;

    const entries = Object.entries(prefillData);
    if (entries.length === 0) entries.push(["", ""]);

    entries.forEach(([key, val], index) => {
      const row = document.createElement('div');
      row.classList.add('input-row');

      const dropdownHTML = `
        <select name="dropdown_${index}" class="dropdown-field">
          <option value="">-- Select --</option>
          ${options.map(option => {
            const selected = val === option ? 'selected' : '';
            return `<option value="${option}" ${selected}>${option}</option>`;
          }).join('')}
        </select>
      `;

      row.innerHTML = `
        <input type="text" name="field_${index}" placeholder="Enter value" class="text-field" value="${key}" />
        ${dropdownHTML}
        <button type="button" class="deleteRowBtn btn btn-sm btn-danger" style="margin-left:10px;border: 0;background: none;cursor: pointer;">
          <i class="fas fa-trash-alt"></i>
        </button>
      `;

      inputSection.appendChild(row);
    });

    inputSection.innerHTML += `
      <div style="margin-top: 10px;">
        <button type="button" id="addInputBtn" class="btn btn-sm btn-secondary button">+ Add Another</button>
        <button type="button" id="saveMappingBtn" class="btn btn-sm btn-secondary button" style="margin-left: 10px;">Save Mapping</button>
        <span id="saveStatus" style="margin-left: 10px; color: green;"></span>
      </div>
    `;

    container.appendChild(inputSection);
  }

  document.addEventListener('click', function (e) {
    // Add new row
    if (e.target.id === 'addInputBtn') {
      const section = document.getElementById('dynamicInputSection');
      const inputCount = section.querySelectorAll('.input-row').length;

      const row = document.createElement('div');
      row.classList.add('input-row');

      const dropdownHTML = `
        <select name="dropdown_${inputCount}" class="dropdown-field">
          <option value="">-- Select --</option>
          ${options.map(option => `<option value="${option}">${option}</option>`).join('')}
        </select>
      `;

      row.innerHTML = `
        <input type="text" name="field_${inputCount}" placeholder="Enter value" class="text-field" />
        ${dropdownHTML}
        <button type="button" class="deleteRowBtn btn btn-sm btn-danger" style="margin-left:10px;border: 0;background: none;cursor: pointer;">
          <i class="fas fa-trash-alt"></i>
        </button>
      `;

      section.insertBefore(row, document.getElementById('addInputBtn').parentNode);
    }

    // Save Mapping
    if (e.target.id === 'saveMappingBtn') {
      const mapping = {};
      const keyCount = {}; // To keep track of how many times a key appears
      const rows = document.querySelectorAll('.input-row');
    
      rows.forEach(row => {
        const input = row.querySelector('input');
        const select = row.querySelector('select');
        if (!input || !select) return;
    
        let key = input.value.trim();
        const value = select.value.trim();
    
        if (!key || !value) return;
    
        // Check and update key name if duplicate
        if (keyCount[key]) {
          keyCount[key] += 1;
          key = `${key}_${keyCount[key]}`;
        } else {
          keyCount[key] = 1;
        }
    
        mapping[key] = value;
      });
    
      const textarea = document.querySelector('#id_extra_data');
      if (textarea) {
        textarea.value = JSON.stringify(mapping, null, 2);
        document.getElementById('saveStatus').textContent = '✅ Mapping set in extra_data';
      } else {
        document.getElementById('saveStatus').textContent = 'extra_data field missing';
      }
    }
    

    // Delete row
    if (e.target.closest('.deleteRowBtn')) {
      const rowToDelete = e.target.closest('.input-row');
      if (rowToDelete) rowToDelete.remove();
    }
  });
});
