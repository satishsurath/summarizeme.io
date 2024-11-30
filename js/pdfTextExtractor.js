import * as pdfjsLib from 'vendor/pdfjs/build/pdf.mjs';

class PDFTextExtractor {
    static async extractTextFromPDF(file) {
        return new Promise(async (resolve, reject) => {
            try {
                // Configure PDF.js with additional options
                const loadingTask = pdfjsLib.getDocument({
                    data: await file.arrayBuffer(),
                    isEvalSupported: false,  // Improve security
                    standardFontDataUrl: 'vendor/pdfjs/standard_fonts/'
                });

                const pdf = await loadingTask.promise;
                const textPromises = Array.from({length: pdf.numPages}, 
                    async (_, i) => {
                        const page = await pdf.getPage(i + 1);
                        const textContent = await page.getTextContent();
                        return textContent.items
                            .map(item => item.str)
                            .filter(str => str.trim() !== '')
                            .join(' ');
                    }
                );

                const pageTexts = await Promise.all(textPromises);
                resolve(pageTexts.join('\n'));

            } catch (error) {
                reject(`PDF Extraction Error: ${error.message}`);
            }
        });
    }

    // Optional: Add metadata extraction
    static async extractPDFMetadata(file) {
        try {
            const loadingTask = pdfjsLib.getDocument({data: await file.arrayBuffer()});
            const pdf = await loadingTask.promise;
            
            return {
                numPages: pdf.numPages,
                // You can extract more metadata from pdf.documentInfo
                documentInfo: await pdf.getMetadata()
            };
        } catch (error) {
            console.error('Metadata extraction error', error);
            return null;
        }
    }
}