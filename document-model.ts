interface DocumentModel {
    id?: string;                // Unique identifier
    name: string;               // Original filename
    type: 'pdf' | 'youtube' | 'txt'; // Extensible document type
    extractedText: string;      // Extracted text content
    uploadedAt: Date;           // Timestamp of upload
    fileSize: number;           // File size in bytes
    metadata?: {                // Flexible metadata structure
        [key: string]: any;
    };
}

interface ExtractionMetadata {
    pageCount?: number;
    language?: string;
    extractionMethod: 'pdfparse' | 'ocr' | 'youtube_api';
}
