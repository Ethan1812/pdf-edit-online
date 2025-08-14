import os
from flask import Flask, render_template_string, request, send_file, jsonify
import fitz  # PyMuPDF
import io
import base64
import json
import zipfile
import uuid

app = Flask(__name__)

# Diccionario global para almacenar los PDFs originales y sus metadatos
# NOTA: Para una aplicación en producción, esto no es escalable ni seguro.
# Se recomienda usar una base de datos o un sistema de archivos temporal.
original_pdfs = {}


def apply_edits_to_page(doc_data, page_num, edits):
    """Aplica ediciones (texto, formas, imágenes) a una página de PDF."""
    try:
        # Abrir el documento original en memoria
        pdf_document = fitz.open(stream=doc_data, filetype="pdf")
        page = pdf_document.load_page(page_num)

        # Escalar coordenadas del cliente a las del PDF
        page_rect = page.rect
        page_width, page_height = page_rect.width, page_rect.height

        # El cliente trabaja con un ancho fijo de 800px, necesitamos el ratio
        scale_factor = page_width / 800

        for element in edits:
            x, y = element['x'] * scale_factor, element['y'] * scale_factor
            width, height = element['width'] * scale_factor, element[
                'height'] * scale_factor

            if element['type'] == 'text':
                font_size = element['fontSize'] * scale_factor
                text = element['text']
                color_hex = element['fontColor']
                color_rgb = tuple(
                    int(color_hex[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

                # Ajustar el punto de inserción para que no se "corte" el texto
                text_bbox = page.insert_textbox(
                    fitz.Rect(
                        x, y, x + width, y +
                        height),  # El ancho y alto son estimados en el cliente
                    text,
                    fontname="helv",  # Usar una fuente estándar
                    fontsize=font_size,
                    color=color_rgb)

            elif element['type'] == 'image':
                img_data = base64.b64decode(element['src'].split(',')[1])
                page.insert_image(fitz.Rect(x, y, x + width, y + height),
                                  stream=img_data)

            elif element['type'] == 'rect':
                fill_color_hex = element['fillColor']
                border_color_hex = element['borderColor']
                fill_color_rgb = tuple(
                    int(fill_color_hex[i:i + 2], 16) / 255.0
                    for i in (1, 3, 5))
                border_color_rgb = tuple(
                    int(border_color_hex[i:i + 2], 16) / 255.0
                    for i in (1, 3, 5))

                page.draw_rect(fitz.Rect(x, y, x + width, y + height),
                               fill=fill_color_rgb,
                               color=border_color_rgb,
                               width=1)

            elif element['type'] == 'circle':
                fill_color_hex = element['fillColor']
                border_color_hex = element['borderColor']
                fill_color_rgb = tuple(
                    int(fill_color_hex[i:i + 2], 16) / 255.0
                    for i in (1, 3, 5))
                border_color_rgb = tuple(
                    int(border_color_hex[i:i + 2], 16) / 255.0
                    for i in (1, 3, 5))

                page.draw_oval(fitz.Rect(x, y, x + width, y + height),
                               fill=fill_color_rgb,
                               color=border_color_rgb,
                               width=1)

        # Guardar la página modificada en un nuevo documento en memoria
        output_buffer = io.BytesIO()
        modified_doc = fitz.open()
        modified_doc.insert_pdf(pdf_document,
                                from_page=page_num,
                                to_page=page_num)
        modified_doc.save(output_buffer)
        modified_doc.close()
        pdf_document.close()

        return output_buffer.getvalue()

    except Exception as e:
        print(f"Error al aplicar ediciones a la página {page_num}: {e}")
        return None


@app.route('/')
def index():
    """Ruta principal que muestra el formulario HTML."""
    return render_template_string(HTML_FORM)


@app.route('/upload', methods=['POST'])
def upload_files():
    """Carga inicial de uno o más PDFs."""
    files = request.files.getlist('pdf_files')
    if not files:
        return jsonify({"error": "No se subieron archivos"}), 400

    pages_data = {}
    pages_order = []

    for file in files:
        file_bytes = file.read()
        doc_id = str(uuid.uuid4())
        original_pdfs[doc_id] = file_bytes

        pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
        for i in range(pdf_document.page_count):
            page = pdf_document.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')

            page_id = f"{doc_id}_{i}"
            pages_data[page_id] = img_base64
            pages_order.append({"docId": doc_id, "pageNum": i})
        pdf_document.close()

    return jsonify({"pagesData": pages_data, "pagesOrder": pages_order})


@app.route('/add_pdfs', methods=['POST'])
def add_pdfs():
    """Añade PDFs a la sesión existente."""
    files = request.files.getlist('pdf_files')
    if not files:
        return jsonify({"error": "No se subieron archivos"}), 400

    pages_data = {}
    pages_order = []

    for file in files:
        file_bytes = file.read()
        doc_id = str(uuid.uuid4())
        original_pdfs[doc_id] = file_bytes

        pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
        for i in range(pdf_document.page_count):
            page = pdf_document.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')

            page_id = f"{doc_id}_{i}"
            pages_data[page_id] = img_base64
            pages_order.append({"docId": doc_id, "pageNum": i})
        pdf_document.close()

    return jsonify({"pagesData": pages_data, "pagesOrder": pages_order})


@app.route('/download_final_pdf', methods=['POST'])
def download_final_pdf():
    """Combina todas las páginas editadas en un solo PDF final."""
    data = request.json
    pages_order = data.get('pages_order', [])
    all_elements_data = data.get('all_elements_data', {})

    final_pdf = fitz.open()

    for page_info in pages_order:
        doc_id = page_info['docId']
        page_num = page_info['pageNum']
        page_id = f"{doc_id}_{page_num}"

        if doc_id not in original_pdfs:
            continue

        doc_data = original_pdfs[doc_id]
        edits = all_elements_data.get(page_id, [])

        if edits:
            modified_page_bytes = apply_edits_to_page(doc_data, page_num,
                                                      edits)
            if modified_page_bytes:
                temp_doc = fitz.open(stream=modified_page_bytes,
                                     filetype="pdf")
                final_pdf.insert_pdf(temp_doc)
                temp_doc.close()
        else:
            temp_doc = fitz.open(stream=doc_data, filetype="pdf")
            final_pdf.insert_pdf(temp_doc,
                                 from_page=page_num,
                                 to_page=page_num)
            temp_doc.close()

    output_buffer = io.BytesIO()
    final_pdf.save(output_buffer)
    final_pdf.close()
    output_buffer.seek(0)

    return send_file(output_buffer,
                     as_attachment=True,
                     download_name='documento_final.pdf',
                     mimetype='application/pdf')


@app.route('/extract_pages', methods=['POST'])
def extract_pages():
    """Extrae páginas específicas de los documentos cargados."""
    data = request.json
    pages_to_extract = data.get('pages', [])
    pages_order = data.get('pages_order', [])
    all_elements_data = data.get('all_elements_data', {})

    if not pages_to_extract:
        return "No se especificaron páginas para extraer.", 400

    extraction_pdf = fitz.open()

    for page_num in pages_to_extract:
        if page_num > 0 and page_num <= len(pages_order):
            page_info = pages_order[page_num -
                                    1]  # Convertir de 1-based a 0-based
            doc_id = page_info['docId']
            original_page_num = page_info['pageNum']
            page_id = f"{doc_id}_{original_page_num}"

            if doc_id not in original_pdfs:
                continue

            doc_data = original_pdfs[doc_id]
            edits = all_elements_data.get(page_id, [])

            if edits:
                modified_page_bytes = apply_edits_to_page(
                    doc_data, original_page_num, edits)
                if modified_page_bytes:
                    temp_doc = fitz.open(stream=modified_page_bytes,
                                         filetype="pdf")
                    extraction_pdf.insert_pdf(temp_doc)
                    temp_doc.close()
            else:
                temp_doc = fitz.open(stream=doc_data, filetype="pdf")
                extraction_pdf.insert_pdf(temp_doc,
                                          from_page=original_page_num,
                                          to_page=original_page_num)
                temp_doc.close()

    if not extraction_pdf.page_count:
        return "No se pudieron extraer las páginas seleccionadas.", 404

    output_buffer = io.BytesIO()
    extraction_pdf.save(output_buffer)
    extraction_pdf.close()
    output_buffer.seek(0)

    return send_file(output_buffer,
                     as_attachment=True,
                     download_name='documento_extraido.pdf',
                     mimetype='application/pdf')


@app.route('/split_all_pages', methods=['POST'])
def split_all_pages():
    """Divide cada página editada en un PDF individual y los comprime en un ZIP."""
    data = request.json
    pages_order = data.get('pages_order', [])
    all_elements_data = data.get('all_elements_data', {})

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, page_info in enumerate(pages_order):
            doc_id = page_info['docId']
            page_num = page_info['pageNum']
            page_id = f"{doc_id}_{page_num}"

            if doc_id not in original_pdfs:
                continue

            doc_data = original_pdfs[doc_id]
            edits = all_elements_data.get(page_id, [])

            # Crear un PDF de una sola página
            if edits:
                modified_page_bytes = apply_edits_to_page(
                    doc_data, page_num, edits)
                if modified_page_bytes:
                    zip_file.writestr(f"pagina_{i+1}.pdf", modified_page_bytes)
            else:
                temp_doc = fitz.open(stream=doc_data, filetype="pdf")
                single_page_doc = fitz.open()
                single_page_doc.insert_pdf(temp_doc,
                                           from_page=page_num,
                                           to_page=page_num)
                temp_doc.close()

                output_buffer = io.BytesIO()
                single_page_doc.save(output_buffer)
                single_page_doc.close()

                zip_file.writestr(f"pagina_{i+1}.pdf",
                                  output_buffer.getvalue())

    zip_buffer.seek(0)
    return send_file(zip_buffer,
                     as_attachment=True,
                     download_name='paginas_separadas.zip',
                     mimetype='application/zip')


# --- Contenido HTML y JavaScript (Corregido y Completado) ---

HTML_FORM = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Editor y Combinador de PDF</title>
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" integrity="sha512-SnH5WK+bZxgPHs44uWIX+LLJAJ9/2PkPKZ5QiAj6Ta86w+fsb2TkcmShkL7S7pE/F+VwE/K3M+Tq/8w/t3P9Sg==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    <style>
        :root {
            --dragon-orange: #f77f00; /* Naranja del uniforme */
            --kamehameha-blue: #428bca; /* Azul del Kamehameha */
            --kaioken-red: #dc3545; /* Rojo del Kaioken */
            --super-saiyan-yellow: #ffc107; /* Amarillo/Dorado del aura */
            --background-dark: #1f1f1f; /* Fondo oscuro */
            --card-bg: #2c2c2c; /* Fondo de las tarjetas */
            --text-light: #f5f5f5; /* Texto claro */
            --text-faded: #cccccc; /* Texto secundario */
            --border-color: #555555; /* Color de los bordes */
            --danger-color: var(--kaioken-red); /* Rojo para acciones peligrosas */
        }

        body {
            font-family: 'Bebas Neue', 'Arial Black', sans-serif;
            text-align: center;
            margin: 0;
            padding: 40px 15px;
            background-color: var(--background-dark);
            color: var(--text-light);
            line-height: 1.6;
        }

        .container {
            max-width: 1100px;
            margin: auto;
            padding: 30px;
            background-color: var(--card-bg);
            border-radius: 15px;
            border: 3px solid var(--dragon-orange);
            box-shadow: 0 0 25px rgba(247, 127, 0, 0.4);
            transition: all 0.3s ease;
        }

        h1 {
            font-family: 'Bebas Neue', sans-serif;
            color: var(--dragon-orange);
            font-size: 4em;
            letter-spacing: 2px;
            text-shadow: 2px 2px 5px rgba(0, 0, 0, 0.5), 0 0 10px var(--super-saiyan-yellow);
            margin-bottom: 5px;
            transition: color 0.3s ease;
        }

        p {
            font-family: 'Arial', sans-serif;
            color: var(--text-faded);
            font-size: 1.1em;
            margin-bottom: 30px;
        }

        .file-upload-label, button {
            font-family: 'Bebas Neue', sans-serif;
            padding: 15px 30px;
            font-size: 1.2em;
            letter-spacing: 1px;
            color: var(--background-dark);
            background-color: var(--dragon-orange);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-transform: uppercase;
            font-weight: bold;
            position: relative;
            z-index: 1;
            overflow: hidden;
            border: 2px solid transparent;
        }

        .file-upload-label:before, button:before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            background: rgba(66, 139, 202, 0.2);
            border-radius: 50%;
            transition: all 0.4s ease;
            transform: translate(-50%, -50%);
            z-index: -1;
        }

        .file-upload-label:hover, button:hover {
            background-color: var(--kamehameha-blue);
            color: var(--text-light);
            border-color: var(--super-saiyan-yellow);
            box-shadow: 0 0 15px var(--super-saiyan-yellow);
            transform: translateY(-3px);
        }

        .file-upload-label:hover:before, button:hover:before {
            width: 200px;
            height: 200px;
            opacity: 0;
        }

        #reset-files-btn {
            background-color: var(--danger-color);
        }
        #reset-files-btn:hover {
            background-color: #a31120;
            border-color: var(--text-light);
            box-shadow: 0 0 15px var(--text-light);
        }

        #tools {
            margin-top: 30px;
            padding: 25px;
            background-color: #242424;
            border-radius: 12px;
            border: 2px solid var(--border-color);
            box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.5);
        }

        .tool-group {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }

        #tools input, #tools select, #tools input::-webkit-color-swatch-wrapper {
            font-family: 'Arial', sans-serif;
            border: 2px solid var(--border-color);
            padding: 10px 15px;
            border-radius: 6px;
            background-color: var(--background-dark);
            color: var(--text-light);
            font-size: 1em;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        #tools input:focus, #tools select:focus, #tools input::-webkit-color-swatch-wrapper:focus {
            border-color: var(--kamehameha-blue);
            box-shadow: 0 0 8px rgba(66, 139, 202, 0.5);
            outline: none;
        }

        #text-input {
            width: 200px;
        }

        #pdf-thumbnails {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 20px;
            margin-top: 40px;
        }

        .page-thumbnail {
            border: 2px solid var(--border-color);
            border-radius: 8px;
            padding: 10px;
            cursor: pointer;
            transition: all 0.3s ease;
            background-color: var(--card-bg);
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.3);
            width: 150px;
            height: auto;
        }

        .page-thumbnail img {
            display: block;
            width: 100%;
            border-radius: 6px;
            border: 1px solid var(--border-color);
        }

        .page-thumbnail.selected-thumb {
            border-color: var(--dragon-orange);
            box-shadow: 0 0 15px var(--dragon-orange), 0 0 5px rgba(255, 255, 255, 0.5);
            transform: scale(1.08);
        }

        .page-thumbnail:hover {
            transform: scale(1.05);
            border-color: var(--kamehameha-blue);
            box-shadow: 0 0 15px var(--kamehameha-blue);
        }

        #page-container {
            position: relative;
            width: 100%;
            max-width: 800px;
            margin: 40px auto;
            border: 3px solid var(--border-color);
            box-shadow: 0 0 20px rgba(0,0,0,0.7);
            border-radius: 12px;
            overflow: hidden;
            background-color: var(--card-bg);
            user-select: none; /* Evita la selección de texto durante el arrastre */
        }

        #page-image {
            width: 100%;
            height: auto;
            display: block;
        }

        .added-element {
            position: absolute;
            cursor: move;
            border: 2px dashed transparent;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
            box-sizing: border-box;
        }

        .added-element.selected {
            border-color: var(--super-saiyan-yellow);
            box-shadow: 0 0 10px var(--super-saiyan-yellow);
        }

        .added-text {
            white-space: pre;
            font-family: 'Arial', sans-serif;
            text-align: left;
            padding: 5px;
        }

        .resizer {
            position: absolute;
            width: 15px;
            height: 15px;
            background: var(--dragon-orange);
            border: 3px solid var(--card-bg);
            border-radius: 50%;
            z-index: 100;
            opacity: 0;
            transition: opacity 0.2s ease;
        }

        .added-element.selected .resizer {
            opacity: 1;
        }

        .resizer.bottom-right {
            right: -8px;
            bottom: -8px;
            cursor: nwse-resize;
        }

        footer {
            margin-top: 60px;
            font-size: 1em;
            color: var(--text-faded);
        }

        @media (max-width: 768px) {
            .container {
                padding: 15px;
            }
            h1 {
                font-size: 3em;
            }
            .tool-group {
                flex-direction: column;
            }
            #tools button, #tools select, #tools input {
                width: 100%;
                box-sizing: border-box;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>EDITOR Y COMBINADOR DE PDF</h1>
        <p>Sube, edita y fusiona tus documentos PDF.</p>

        <label for="pdf-files" class="file-upload-label">Cargar PDFs</label>
        <input type="file" id="pdf-files" name="pdf_files" accept=".pdf" multiple style="display: none;">
        <button id="reset-files-btn" style="display: none;">Reiniciar</button>

        <div id="tools">
            <div class="tool-group">
                <input type="text" id="text-input" placeholder="Escribe el texto">
                <select id="font-size">
                    <option value="12">12pt</option>
                    <option value="14">14pt</option>
                    <option value="16">16pt</option>
                    <option value="18">18pt</option>
                    <option value="24">24pt</option>
                </select>
                <label for="font-color">Color:</label>
                <input type="color" id="font-color" value="#feca34">
                <button id="bold-btn">B</button>
                <button id="italic-btn">I</button>
                <button id="add-text-btn">Añadir Texto</button>
            </div>
            <div class="tool-group">
                <label for="image-upload" class="file-upload-label">
                    <i class="fas fa-image"></i> Subir Imagen/Firma
                </label>
                <input type="file" id="image-upload" accept="image/*" style="display: none;">
            </div>
            <div class="tool-group">
                <label for="fill-color">Relleno:</label>
                <input type="color" id="fill-color" value="#007bff">
                <label for="border-color">Borde:</label>
                <input type="color" id="border-color" value="#f77f00">
                <button id="add-rect-btn">Añadir Rectángulo</button>
                <button id="add-circle-btn">Añadir Círculo</button>
            </div>
            <div class="tool-group">
                <button id="delete-element-btn">Eliminar Elemento</button>
                <button id="delete-page-btn">Eliminar Página</button>
                <button id="download-final-pdf-btn" style="display: none;">Descargar PDF Final</button>
            </div>
            <div class="tool-group">
                <input type="text" id="extract-pages-input" placeholder="Ej: 1, 3, 5-8">
                <button id="extract-pages-btn">Extraer Páginas</button>
                <button id="split-all-btn">Dividir en todas las páginas</button>
            </div>
        </div>
        <div id="pdf-thumbnails"></div>
        <div id="page-container">
            <img id="page-image" src="" alt="Página del PDF">
        </div>
    </div>
    <footer>
        <p>Desarrollado por Yeisson Rincon</p>
        <p>&copy; 2025 Todos los derechos reservados.</p>
    </footer>
    <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.14.0/Sortable.min.js"></script>
    <script>
        let uploadedPdfs = { pagesData: {}, pagesOrder: [] };
        let currentDocumentId = null;
        let currentPageIndex = 0;
        let editedElements = {};
        let isDragging = false;
        let draggedElement = null;
        let isResizing = false;
        let selectedElement = null;
        let startX, startY, startWidth, startHeight, startLeft, startTop;
        let fontStyle = {
            bold: false,
            italic: false
        };

        const pageContainer = document.getElementById('page-container');
        const thumbnailsContainer = document.getElementById('pdf-thumbnails');
        const downloadFinalPdfBtn = document.getElementById('download-final-pdf-btn');
        const resetFilesBtn = document.getElementById('reset-files-btn');
        const pdfFilesInput = document.getElementById('pdf-files');
        const boldBtn = document.getElementById('bold-btn');
        const italicBtn = document.getElementById('italic-btn');

        let sortableInstance = null;

        function initSortable() {
            if (sortableInstance) {
                sortableInstance.destroy();
            }
            sortableInstance = new Sortable(thumbnailsContainer, {
                animation: 150,
                onUpdate: function (evt) {
                    const newThumbsData = Array.from(thumbnailsContainer.children).map(el => el.getAttribute('data-page-id'));
                    let newPagesOrder = [];
                    newThumbsData.forEach(id => {
                        const [doc, page] = id.split('_');
                        newPagesOrder.push({ docId: doc, pageNum: parseInt(page) });
                    });
                    uploadedPdfs.pagesOrder = newPagesOrder;
                }
            });
        }

        function updateElementPositionAndSize(element, x, y, width, height) {
            const pageId = `${currentDocumentId}_${currentPageIndex}`;
            const elementData = (editedElements[pageId] || []).find(data => data.element === element);
            if (elementData) {
                elementData.x = x;
                elementData.y = y;
                elementData.width = width;
                elementData.height = height;
                element.style.left = `${x}px`;
                element.style.top = `${y}px`;
                element.style.width = `${width}px`;
                element.style.height = `${height}px`;
            }
        }

        function displayPage(docId, pageIndex) {
            const pageId = `${docId}_${pageIndex}`;
            const pageData = uploadedPdfs.pagesData[pageId];

            pageContainer.innerHTML = '';

            const mainPageImage = document.createElement('img');
            mainPageImage.id = 'page-image';
            mainPageImage.src = `data:image/png;base64,${pageData}`;
            pageContainer.appendChild(mainPageImage);

            currentDocumentId = docId;
            currentPageIndex = pageIndex;
            selectedElement = null;

            document.querySelectorAll('.page-thumbnail').forEach(thumb => {
                thumb.classList.remove('selected-thumb');
            });
            const selectedThumb = document.querySelector(`[data-page-id="${pageId}"]`);
            if (selectedThumb) {
                selectedThumb.classList.add('selected-thumb');
            }

            const currentPageEdits = editedElements[pageId] || [];
            if (currentPageEdits.length > 0) {
                currentPageEdits.forEach(elementData => {
                    let newElement = createEditableElement(elementData);
                    pageContainer.appendChild(newElement);
                    elementData.element = newElement;
                });
            }
            pageContainer.style.display = 'block';
        }

        function createEditableElement(elementData) {
            let newElement = document.createElement('div');
            newElement.className = 'added-element';

            if (elementData.type === 'text') {
                newElement.classList.add('added-text');
                newElement.textContent = elementData.text;
                newElement.style.fontSize = `${elementData.fontSize}px`;
                newElement.style.color = elementData.fontColor;
                newElement.style.fontWeight = elementData.bold ? 'bold' : 'normal';
                newElement.style.fontStyle = elementData.italic ? 'italic' : 'normal';
            } else if (elementData.type === 'image') {
                newElement.classList.add('added-image');
                let img = document.createElement('img');
                img.src = elementData.src;
                img.style.width = '100%';
                img.style.height = '100%';
                newElement.appendChild(img);
            } else if (elementData.type === 'rect') {
                newElement.classList.add('added-rect');
                newElement.style.backgroundColor = elementData.fillColor;
                newElement.style.border = `1px solid ${elementData.borderColor}`;
            } else if (elementData.type === 'circle') {
                newElement.classList.add('added-circle');
                newElement.style.backgroundColor = elementData.fillColor;
                newElement.style.border = `1px solid ${elementData.borderColor}`;
                newElement.style.borderRadius = '50%';
            }

            newElement.style.left = `${elementData.x}px`;
            newElement.style.top = `${elementData.y}px`;
            newElement.style.width = `${elementData.width}px`;
            newElement.style.height = `${elementData.height}px`;

            if (elementData.type !== 'text') {
                const resizer = document.createElement('div');
                resizer.className = 'resizer bottom-right';
                newElement.appendChild(resizer);
                resizer.addEventListener('mousedown', function(e) {
                    isResizing = true;
                    draggedElement = newElement;
                    selectElement(newElement);

                    const elementRect = draggedElement.getBoundingClientRect();
                    startWidth = elementRect.width;
                    startHeight = elementRect.height;
                    startX = e.clientX;
                    startY = e.clientY;

                    e.stopPropagation();
                    e.preventDefault();
                });
            }

            newElement.addEventListener('mousedown', function(e) {
                if (e.target.classList.contains('resizer')) return;
                isDragging = true;
                draggedElement = newElement;
                selectElement(newElement);

                const elementRect = draggedElement.getBoundingClientRect();
                startX = e.clientX;
                startY = e.clientY;
                startLeft = elementRect.left - pageContainer.getBoundingClientRect().left;
                startTop = elementRect.top - pageContainer.getBoundingClientRect().top;

                e.preventDefault();
            });

            return newElement;
        }

        function renderThumbnails() {
            thumbnailsContainer.innerHTML = '';
            uploadedPdfs.pagesOrder.forEach(pageInfo => {
                const pageId = `${pageInfo.docId}_${pageInfo.pageNum}`;

                const thumbWrapper = document.createElement('div');
                thumbWrapper.className = 'page-thumbnail';
                thumbWrapper.setAttribute('data-page-id', pageId);

                const img = document.createElement('img');
                img.src = `data:image/png;base64,${uploadedPdfs.pagesData[pageId]}`;
                img.alt = `Página ${pageInfo.pageNum + 1}`;

                thumbWrapper.appendChild(img);
                thumbWrapper.addEventListener('click', () => {
                    displayPage(pageInfo.docId, pageInfo.pageNum);
                });
                thumbnailsContainer.appendChild(thumbWrapper);
            });

            if (uploadedPdfs.pagesOrder.length > 0) {
                const firstPageInfo = uploadedPdfs.pagesOrder[0];
                displayPage(firstPageInfo.docId, firstPageInfo.pageNum);
                downloadFinalPdfBtn.style.display = 'block';
                resetFilesBtn.style.display = 'inline-block';
            } else {
                pageContainer.style.display = 'none';
                downloadFinalPdfBtn.style.display = 'none';
                resetFilesBtn.style.display = 'none';
            }
        }

        async function uploadFiles(files) {
            if (files.length === 0) return;

            const formData = new FormData();
            for(let i = 0; i < files.length; i++) {
                formData.append('pdf_files', files[i]);
            }

            const isFreshUpload = uploadedPdfs.pagesOrder.length === 0;
            const endpoint = isFreshUpload ? '/upload' : '/add_pdfs';

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`Server responded with status ${response.status}`);
                }

                const responseData = await response.json();

                if (isFreshUpload) {
                    uploadedPdfs = responseData;
                    editedElements = {};
                } else {
                    Object.assign(uploadedPdfs.pagesData, responseData.pagesData);
                    uploadedPdfs.pagesOrder = uploadedPdfs.pagesOrder.concat(responseData.pagesOrder);
                }

                if (uploadedPdfs.pagesOrder.length > 0) {
                    renderThumbnails();
                    initSortable();
                }

            } catch (error) {
                alert(`Error al cargar el PDF: ${error.message}`);
            }
        }

        pdfFilesInput.addEventListener('change', async function(e) {
            const files = Array.from(e.target.files);
            await uploadFiles(files);
            e.target.value = '';
        });

        resetFilesBtn.addEventListener('click', function() {
            uploadedPdfs = { pagesData: {}, pagesOrder: [] };
            editedElements = {};
            pageContainer.style.display = 'none';
            thumbnailsContainer.innerHTML = '';
            downloadFinalPdfBtn.style.display = 'none';
            resetFilesBtn.style.display = 'none';
            if (sortableInstance) {
                sortableInstance.destroy();
                sortableInstance = null;
            }
        });

        document.getElementById('image-upload').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file || !currentDocumentId) return;

            const reader = new FileReader();
            reader.onload = function(e) {
                const imageSrc = e.target.result;
                const pageId = `${currentDocumentId}_${currentPageIndex}`;
                editedElements[pageId] = editedElements[pageId] || [];

                const newElementData = {
                    type: 'image',
                    x: 50, y: 50, width: 100, height: 100,
                    src: imageSrc,
                    element: null
                };
                editedElements[pageId].push(newElementData);
                displayPage(currentDocumentId, currentPageIndex);
            };
            reader.readAsDataURL(file);
        });

        document.getElementById('add-rect-btn').addEventListener('click', function() {
            if (!currentDocumentId) { alert('Sube un PDF primero.'); return; }
            const fillColor = document.getElementById('fill-color').value;
            const borderColor = document.getElementById('border-color').value;
            const pageId = `${currentDocumentId}_${currentPageIndex}`;
            editedElements[pageId] = editedElements[pageId] || [];

            editedElements[pageId].push({
                type: 'rect', x: 50, y: 50, width: 100, height: 50,
                fillColor: fillColor, borderColor: borderColor, element: null
            });
            displayPage(currentDocumentId, currentPageIndex);
        });

        document.getElementById('add-circle-btn').addEventListener('click', function() {
            if (!currentDocumentId) { alert('Sube un PDF primero.'); return; }
            const fillColor = document.getElementById('fill-color').value;
            const borderColor = document.getElementById('border-color').value;
            const pageId = `${currentDocumentId}_${currentPageIndex}`;
            editedElements[pageId] = editedElements[pageId] || [];

            editedElements[pageId].push({
                type: 'circle', x: 50, y: 50, width: 100, height: 100,
                fillColor: fillColor, borderColor: borderColor, element: null
            });
            displayPage(currentDocumentId, currentPageIndex);
        });

        document.getElementById('add-text-btn').addEventListener('click', async function() {
            if (!currentDocumentId) { alert('Sube un PDF primero.'); return; }
            const textToAdd = document.getElementById('text-input').value;
            if (!textToAdd) { alert('Escribe un texto para añadir.'); return; }

            const pageId = `${currentDocumentId}_${currentPageIndex}`;
            editedElements[pageId] = editedElements[pageId] || [];

            const fontSize = parseInt(document.getElementById('font-size').value);
            const fontColor = document.getElementById('font-color').value;

            // Medir el texto para darle un ancho inicial
            const tempDiv = document.createElement('div');
            tempDiv.style.position = 'absolute';
            tempDiv.style.visibility = 'hidden';
            tempDiv.style.whiteSpace = 'pre';
            tempDiv.style.fontFamily = 'Arial';
            tempDiv.style.fontSize = `${fontSize}px`;
            tempDiv.style.fontWeight = fontStyle.bold ? 'bold' : 'normal';
            tempDiv.style.fontStyle = fontStyle.italic ? 'italic' : 'normal';
            tempDiv.textContent = textToAdd;
            document.body.appendChild(tempDiv);
            const textWidth = tempDiv.offsetWidth + 10;
            const textHeight = tempDiv.offsetHeight + 10;
            document.body.removeChild(tempDiv);

            editedElements[pageId].push({
                type: 'text', text: textToAdd, x: 50, y: 50, width: textWidth, height: textHeight,
                fontSize: fontSize,
                fontColor: fontColor,
                bold: fontStyle.bold, italic: fontStyle.italic, element: null
            });
            displayPage(currentDocumentId, currentPageIndex);
        });

        boldBtn.addEventListener('click', function() {
            fontStyle.bold = !fontStyle.bold;
            boldBtn.style.backgroundColor = fontStyle.bold ? 'var(--super-saiyan-yellow)' : 'var(--dragon-orange)';
        });

        italicBtn.addEventListener('click', function() {
            fontStyle.italic = !fontStyle.italic;
            italicBtn.style.backgroundColor = fontStyle.italic ? 'var(--super-saiyan-yellow)' : 'var(--dragon-orange)';
        });

        document.getElementById('delete-element-btn').addEventListener('click', function() {
            if (!selectedElement) {
                alert('Selecciona un elemento para eliminar.');
                return;
            }
            const pageId = `${currentDocumentId}_${currentPageIndex}`;
            const elementDataIndex = (editedElements[pageId] || []).findIndex(
                data => data.element === selectedElement
            );
            if (elementDataIndex > -1) {
                editedElements[pageId].splice(elementDataIndex, 1);
                selectedElement = null;
                displayPage(currentDocumentId, currentPageIndex);
            }
        });

        document.getElementById('delete-page-btn').addEventListener('click', function() {
            const pageIdToDelete = `${currentDocumentId}_${currentPageIndex}`;
            const pageIndexInOrder = uploadedPdfs.pagesOrder.findIndex(p => `${p.docId}_${p.pageNum}` === pageIdToDelete);

            if (pageIndexInOrder > -1) {
                uploadedPdfs.pagesOrder.splice(pageIndexInOrder, 1);

                delete editedElements[pageIdToDelete];
                delete uploadedPdfs.pagesData[pageIdToDelete];

                const newPageIndex = Math.min(pageIndexInOrder, uploadedPdfs.pagesOrder.length - 1);

                if (uploadedPdfs.pagesOrder.length > 0) {
                    const newPageInfo = uploadedPdfs.pagesOrder[newPageIndex];
                    displayPage(newPageInfo.docId, newPageInfo.pageNum);
                } else {
                    pageContainer.style.display = 'none';
                    downloadFinalPdfBtn.style.display = 'none';
                    resetFilesBtn.style.display = 'none';
                }

                renderThumbnails();
            } else {
                alert('No se puede eliminar la página seleccionada.');
            }
        });

        document.getElementById('download-final-pdf-btn').addEventListener('click', async function() {
            if (uploadedPdfs.pagesOrder.length === 0) {
                alert('No hay páginas para descargar.');
                return;
            }

            // Envía solo los datos necesarios para la descarga
            const downloadData = {
                pages_order: uploadedPdfs.pagesOrder,
                all_elements_data: {}
            };
            for (const pageId in editedElements) {
                if (editedElements[pageId].length > 0) {
                    downloadData.all_elements_data[pageId] = editedElements[pageId].map(element => ({
                        type: element.type,
                        x: element.x,
                        y: element.y,
                        width: element.width,
                        height: element.height,
                        text: element.text,
                        fontSize: element.fontSize,
                        fontColor: element.fontColor,
                        bold: element.bold,
                        italic: element.italic,
                        src: element.src,
                        fillColor: element.fillColor,
                        borderColor: element.borderColor
                    }));
                }
            }

            const response = await fetch('/download_final_pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(downloadData)
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `documento_final.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                alert('PDF descargado con éxito.');
            } else {
                const errorText = await response.text();
                alert(`Error al descargar el PDF: ${errorText}`);
            }
        });

        document.getElementById('extract-pages-btn').addEventListener('click', async function() {
            const pagesInput = document.getElementById('extract-pages-input').value;
            const pages = parsePageRanges(pagesInput);

            if (pages.length === 0) {
                alert('Formato de páginas no válido. Usa "1, 3, 5-8".');
                return;
            }

            // Envía solo los datos necesarios para la descarga
            const extractData = {
                pages: pages,
                pages_order: uploadedPdfs.pagesOrder,
                all_elements_data: {}
            };
            for (const pageId in editedElements) {
                if (editedElements[pageId].length > 0) {
                    extractData.all_elements_data[pageId] = editedElements[pageId].map(element => ({
                        type: element.type,
                        x: element.x,
                        y: element.y,
                        width: element.width,
                        height: element.height,
                        text: element.text,
                        fontSize: element.fontSize,
                        fontColor: element.fontColor,
                        bold: element.bold,
                        italic: element.italic,
                        src: element.src,
                        fillColor: element.fillColor,
                        borderColor: element.borderColor
                    }));
                }
            }

            const response = await fetch('/extract_pages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(extractData)
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `documento_extraido.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                alert('Páginas extraídas y descargadas con éxito.');
            } else {
                const errorText = await response.text();
                alert(`Error al extraer las páginas: ${errorText}`);
            }
        });

        document.getElementById('split-all-btn').addEventListener('click', async function() {
            if (uploadedPdfs.pagesOrder.length === 0) { alert('Sube un PDF primero.'); return; }

            // Envía solo los datos necesarios para la descarga
            const splitData = {
                pages_order: uploadedPdfs.pagesOrder,
                all_elements_data: {}
            };
            for (const pageId in editedElements) {
                if (editedElements[pageId].length > 0) {
                    splitData.all_elements_data[pageId] = editedElements[pageId].map(element => ({
                        type: element.type,
                        x: element.x,
                        y: element.y,
                        width: element.width,
                        height: element.height,
                        text: element.text,
                        fontSize: element.fontSize,
                        fontColor: element.fontColor,
                        bold: element.bold,
                        italic: element.italic,
                        src: element.src,
                        fillColor: element.fillColor,
                        borderColor: element.borderColor
                    }));
                }
            }

            const response = await fetch('/split_all_pages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(splitData)
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `paginas_separadas.zip`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                alert('PDF dividido y descargado con éxito.');
            } else {
                const errorText = await response.text();
                alert(`Error al dividir todas las páginas: ${errorText}`);
            }
        });

        function parsePageRanges(input) {
            const parts = input.split(',').map(s => s.trim()).filter(s => s.length > 0);
            let pages = [];
            parts.forEach(part => {
                if (part.includes('-')) {
                    const [start, end] = part.split('-').map(Number);
                    if (!isNaN(start) && !isNaN(end) && start <= end) {
                        for (let i = start; i <= end; i++) {
                            pages.push(i);
                        }
                    }
                } else {
                    const pageNum = Number(part);
                    if (!isNaN(pageNum)) {
                        pages.push(pageNum);
                    }
                }
            });
            return [...new Set(pages)].sort((a, b) => a - b);
        }

        function selectElement(element) {
            if (selectedElement && selectedElement !== element) {
                selectedElement.classList.remove('selected');
            }
            selectedElement = element;
            selectedElement.classList.add('selected');
        }

        pageContainer.addEventListener('click', function(e) {
            if (selectedElement && !e.target.closest('.added-element')) {
                selectedElement.classList.remove('selected');
                selectedElement = null;
            }
        });

        document.addEventListener('mousemove', function(e) {
            if (!draggedElement) return;

            const pageContainerRect = pageContainer.getBoundingClientRect();

            if (isResizing) {
                const newWidth = Math.max(10, e.clientX - startX + startWidth);
                const newHeight = Math.max(10, e.clientY - startY + startHeight);

                updateElementPositionAndSize(
                    draggedElement,
                    startLeft,
                    startTop,
                    newWidth,
                    newHeight
                );
            } else if (isDragging) {
                const newLeft = e.clientX - startX + startLeft;
                const newTop = e.clientY - startY + startTop;

                updateElementPositionAndSize(
                    draggedElement,
                    newLeft,
                    newTop,
                    draggedElement.offsetWidth,
                    draggedElement.offsetHeight
                );
            }
        });

        document.addEventListener('mouseup', function() {
            isDragging = false;
            isResizing = false;
            draggedElement = null;
        });

        // Inicializar el renderizado si hay algo en el historial de navegación
        window.onload = function() {
            if (uploadedPdfs.pagesOrder.length > 0) {
                renderThumbnails();
            }
        };
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True)
