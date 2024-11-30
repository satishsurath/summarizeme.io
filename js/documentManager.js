import { IndexedDBService } from '/js/indexedDBService.js';
import { PDFTextExtractor } from '/js/pdfTextExtractor.js';

class DocumentManager {
    constructor() {
        this.indexedDBService = new IndexedDBService();
        this.initEventListeners();
        this.loadUploadHistory();
    }

    initEventListeners() {
        const fileUpload = document.getElementById('fileUpload');
        fileUpload.addEventListener('change', this.handleFileUpload.bind(this));
    }

    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file || file.type !== 'application/pdf') {
            this.showError('Please upload a valid PDF file.');
            return;
        }

        try {
            this.showProgress(0);
            const extractedText = await PDFTextExtractor.extractTextFromPDF(file);
            
            const document = {
                name: file.name,
                type: 'pdf',
                size: file.size,
                rawFile: file,
                extractedText: extractedText
            };

            await this.indexedDBService.addDocument(document);
            this.showProgress(100);
            this.loadUploadHistory();
        } catch (error) {
            this.showError(error);
        }
    }

    async loadUploadHistory() {
        const historyContainer = document.getElementById('historyContainer');
        historyContainer.innerHTML = '';

        const documents = await this.indexedDBService.getAllDocuments();
        documents.forEach(doc => {
            const docCard = this.createDocumentCard(doc);
            historyContainer.appendChild(docCard);
        });
    }

    async getFileForDocument(documentId) {
        await this.openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['files'], 'readonly');
            const store = transaction.objectStore('files');
            const request = store.get(documentId);
    
            request.onsuccess = (event) => {
                resolve(event.target.result ? event.target.result.file : null);
            };
    
            request.onerror = (event) => reject(event.target.error);
        });
    }

    createDocumentCard(document) {
        const card = document.createElement('div');
        card.className = 'bg-white shadow-md rounded-lg p-4';
        card.innerHTML = `
            <h3 class="font-bold">${document.name}</h3>
            <p>Type: ${document.type}</p>
            <p>Size: ${(document.size / 1024).toFixed(2)} KB</p>
            <div class="mt-2 flex space-x-2">
                <button onclick="documentManager.previewText('${document.extractedText}', '${document.name}')" 
                        class="bg-blue-500 text-white px-3 py-1 rounded">
                    Preview Text
                </button>
            </div>
        `;
        return card;
    }

    previewText(text, fileName) {
        const modal = document.getElementById('textPreviewModal');
        const titleElement = document.getElementById('modalTitle');
        const contentElement = document.getElementById('textPreviewContent');

        titleElement.textContent = `Text Preview: ${fileName}`;
        contentElement.textContent = text;
        modal.classList.remove('hidden');

        // Add close modal functionality
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
            }
        };
    }

    showProgress(percentage) {
        const progressContainer = document.getElementById('progressContainer');
        const progressBar = document.getElementById('progressBar');
        
        progressContainer.classList.remove('hidden');
        progressBar.style.width = `${percentage}%`;
    }

    showError(message) {
        const errorContainer = document.getElementById('errorContainer');
        errorContainer.textContent = message;
        setTimeout(() => {
            errorContainer.textContent = '';
        }, 5000);
    }
}

// Initialize the document manager
const documentManager = new DocumentManager();