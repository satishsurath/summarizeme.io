class PDFTextExtractor {
    static async extractTextFromPDF(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = async (event) => {
                try {
                    // Use PDF.js (you'll need to include the PDF.js library)
                    const loadingTask = pdfjsLib.getDocument({data: event.target.result});
                    const pdf = await loadingTask.promise;
                    let extractedText = '';

                    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                        const page = await pdf.getPage(pageNum);
                        const textContent = await page.getTextContent();
                        extractedText += textContent.items.map(item => item.str).join(' ') + '\n';
                    }

                    resolve(extractedText);
                } catch (error) {
                    reject(`PDF Extraction Error: ${error.message}`);
                }
            };

            reader.readAsArrayBuffer(file);
        });
    }
}