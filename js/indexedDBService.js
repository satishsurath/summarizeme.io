export class IndexedDBService {
    constructor(dbName = 'DocumentArchive', version = 1) {
        this.dbName = dbName;
        this.version = version;
        this.db = null;
    }

    async openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Create object stores for different document types
                if (!db.objectStoreNames.contains('documents')) {
                    const documentsStore = db.createObjectStore('documents', { 
                        keyPath: 'id', 
                        autoIncrement: true 
                    });

                    // Indexes for efficient querying
                    documentsStore.createIndex('type', 'type', { unique: false });
                    documentsStore.createIndex('uploadDate', 'uploadDate', { unique: false });
                }

                // Add files object store
                if (!db.objectStoreNames.contains('files')) {
                    db.createObjectStore('files', { 
                        keyPath: 'documentId' 
                    });
                }
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                resolve(this.db);
            };

            request.onerror = (event) => {
                reject(`IndexedDB Error: ${event.target.error}`);
            };
        });
    }

    async addDocument(document) {
        await this.openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['documents'], 'readwrite');
            const store = transaction.objectStore('documents');
            
            // Ensure the document can be stored
            const documentEntry = {
                ...document,
                uploadDate: new Date().toISOString(),
                // Convert file to storable format
                rawFile: {
                    name: document.rawFile.name,
                    type: document.rawFile.type,
                    size: document.rawFile.size,
                    lastModified: document.rawFile.lastModified
                }
            };

            // Remove the actual File object, which can't be stored directly
            delete documentEntry.rawFile;

            const request = store.add(documentEntry);

            request.onsuccess = (event) => {
                // Store the actual file separately if needed
                this.storeFileBlob(event.target.result, document.rawFile);
                resolve(event.target.result);
            };

            request.onerror = (event) => {
                reject(`Add Document Error: ${event.target.error}`);
            };
        });
    }

    async storeFileBlob(documentId, file) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['files'], 'readwrite');
            const store = transaction.objectStore('files');

            const fileEntry = {
                documentId: documentId,
                file: file
            };

            const request = store.add(fileEntry);

            request.onsuccess = () => resolve();
            request.onerror = (event) => reject(event.target.error);
        });
    }

    async getAllDocuments() {
        await this.openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['documents'], 'readonly');
            const store = transaction.objectStore('documents');
            const request = store.getAll();

            request.onsuccess = (event) => resolve(event.target.result);
            request.onerror = (event) => reject(event.target.error);
        });
    }
}