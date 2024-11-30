import { IndexedDBService } from './indexedDBService.js';
import { PDFTextExtractor } from './pdfTextExtractor.js';

export class DocumentManager {
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

    createDocumentCard(document1) {
        // Create the card element correctly
        console.log('Creating document card:', document1);
        if (typeof document === 'undefined') {
            throw new Error('document is not available');
        }
        else
        {
        console.log('Creating document card:', document1);
        const card = document1.createElement('div');
        card.className = 'bg-white shadow-md rounded-lg p-4';
        card.innerHTML = `
            <h3 class="font-bold">${document1.name}</h3>
            <p>Type: ${document1.type}</p>
            <p>Size: ${(document1.size / 1024).toFixed(2)} KB</p>
            <div class="mt-2 flex space-x-2">
                <button class="bg-blue-500 text-white px-3 py-1 rounded preview-btn">
                    Preview Text
                </button>
            </div>
        `;
    
        // Add event listener for preview button
        const previewBtn = card.querySelector('.preview-btn');
        previewBtn.addEventListener('click', () => {
            this.previewText(document1.extractedText, document1.name);
        });
    
        return card;
        }
    }
    
    async loadUploadHistory() {
        const historyContainer = document.getElementById('historyContainer');
        
        // Clear existing content
        historyContainer.innerHTML = '';
    
        // Fetch and display documents
        this.indexedDBService.getAllDocuments()
            .then(documents => {
                if (documents.length === 0) {
                    historyContainer.innerHTML = '<p>No documents uploaded yet.</p>';
                    return;
                }
    
                documents.forEach(doc => {
                    const docCard = this.createDocumentCard(doc);
                    historyContainer.appendChild(docCard);
                });
            })
            .catch(error => {
                console.error('Error loading upload history:', error);
                historyContainer.innerHTML = '<p>Error loading documents.</p>';
            });
    }

    previewText(text, fileName) {
        const modal = document.getElementById('textPreviewModal');
        const titleElement = document.getElementById('modalTitle');
        const contentElement = document.getElementById('textPreviewContent');
    
        if (!modal || !titleElement || !contentElement) {
            console.error('Modal elements not found');
            return;
        }
    
        titleElement.textContent = `Text Preview: ${fileName}`;
        contentElement.textContent = text;
        
        // Show modal
        modal.classList.remove('hidden');
    
        // Close modal when clicking outside
        const closeModal = (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
                modal.removeEventListener('click', closeModal);
            }
        };
    
        modal.addEventListener('click', closeModal);
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