# Editor y Combinador de PDF

Una aplicación web completa construida con Flask y JavaScript que permite a los usuarios cargar, editar, fusionar, dividir y gestionar documentos PDF de forma interactiva a través del navegador.

![Demo de la Aplicación](https://i.imgur.com/TU8E8wV.gif) ## Descripción

Este proyecto es una herramienta de edición de PDF todo en uno. Los usuarios pueden cargar múltiples archivos PDF, que se descomponen en páginas individuales. Estas páginas se pueden reorganizar mediante una interfaz de arrastrar y soltar (drag-and-drop). El lienzo de edición principal permite añadir elementos como texto, imágenes (ideal para firmas) y formas geométricas. Finalmente, el proyecto se puede exportar de varias maneras: como un único PDF fusionado, como un subconjunto de páginas extraídas o como un archivo ZIP que contiene cada página como un PDF individual.

La interfaz de usuario es responsiva y presenta un diseño temático inspirado en "Dragon Ball".

## ✨ Características Principales

* **Carga Múltiple de Archivos**: Carga uno o varios documentos PDF a la vez.
* **Fusión de Documentos**: Combina múltiples PDFs en un solo archivo.
* **Organización de Páginas**: Reordena las páginas fácilmente arrastrando y soltando sus miniaturas.
* **Eliminación de Páginas**: Elimina páginas no deseadas con un solo clic.
* **Edición Visual**:
    * **Añadir Texto**: Inserta texto con opciones para cambiar el tamaño y el color.
    * **Insertar Imágenes**: Agrega imágenes o firmas a cualquier página.
    * **Añadir Formas**: Dibuja rectángulos y círculos con colores de borde y relleno personalizables.
* **Manipulación de Elementos**: Mueve, redimensiona y elimina cualquier elemento añadido al lienzo.
* **Múltiples Opciones de Exportación**:
    * **Descargar PDF Final**: Guarda todas las páginas ordenadas y editadas en un único PDF.
    * **Extraer Páginas**: Crea un nuevo PDF con un rango de páginas específico (ej: "1, 3, 5-8").
    * **Dividir Páginas**: Exporta cada página como un PDF individual dentro de un archivo ZIP.

## 🛠️ Stack Tecnológico

* **Backend**:
    * **Python 3**
    * **Flask**: Microframework para el servidor web y la API.
    * **PyMuPDF (fitz)**: Biblioteca para la manipulación robusta de archivos PDF.
* **Frontend**:
    * HTML5
    * CSS3 (con variables para tematización)
    * **JavaScript (Vanilla)**: Para toda la lógica del cliente, interacciones y comunicación con la API.
* **Librerías Externas**:
    * **SortableJS**: Para la funcionalidad de arrastrar y soltar las miniaturas de las páginas.

## 🚀 Instalación y Puesta en Marcha

Sigue estos pasos para ejecutar el proyecto en tu máquina local.

1.  **Clona el repositorio:**
    ```bash
    git clone [https://github.com/tu-usuario/tu-repositorio.git](https://github.com/tu-usuario/tu-repositorio.git)
    cd tu-repositorio
    ```

2.  **Crea y activa un entorno virtual (recomendado):**
    ```bash
    # Para Windows
    python -m venv venv
    .\venv\Scripts\activate

    # Para macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Instala las dependencias de Python:**
    ```bash
    pip install Flask PyMuPDF
    ```

4.  **Ejecuta la aplicación Flask:**
    Suponiendo que el archivo principal se llama `app.py`:
    ```bash
    python app.py
    ```

5.  **Abre la aplicación en tu navegador:**
    Visita la siguiente URL: `http://12.0.0.1:5000`

## 📋 Uso

1.  Haz clic en **"Cargar PDFs"** para seleccionar los archivos que deseas editar.
2.  Usa las miniaturas en la parte inferior para seleccionar una página o para reordenarlas.
3.  Utiliza la barra de herramientas superior para añadir texto, imágenes o formas a la página seleccionada.
4.  Haz clic sobre cualquier elemento añadido para seleccionarlo, moverlo, redimensionarlo o eliminarlo.
5.  Cuando hayas terminado, utiliza los botones de la sección de herramientas para **"Descargar PDF Final"**, **"Extraer Páginas"** o **"Dividir en todas las páginas"**.

## 🔌 API Endpoints

La aplicación expone los siguientes endpoints para ser consumidos por el frontend:

* `GET /`: Sirve la página principal de la aplicación (el editor).
* `POST /upload`: Maneja la carga inicial de archivos PDF.
* `POST /add_pdfs`: Añade archivos PDF adicionales a la sesión actual.
* `POST /download_final_pdf`: Combina, edita y devuelve el documento PDF final.
* `POST /extract_pages`: Devuelve un PDF con las páginas extraídas.
* `POST /split_all_pages`: Devuelve un archivo ZIP con todas las páginas como PDFs individuales.
