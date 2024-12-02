<?php
namespace PDFTextExtractor;

use Smalot\PdfParser\Parser;
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

class DocumentProcessor {
    private const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB limit
    private const ALLOWED_MIME_TYPES = [
        'application/pdf' => 'pdf',
        'text/plain' => 'txt'
    ];

    public function processUpload(array $file): ?array {
        try {
            // Validate file
            $this->validateUpload($file);

            // Extract text based on file type
            $extractedText = $this->extractText($file);

            // Generate metadata
            $metadata = $this->generateMetadata($file, $extractedText);

            return [
                'document' => [
                    'name' => $file['name'],
                    'type' => $this->detectFileType($file),
                    'extractedText' => $extractedText,
                    'metadata' => $metadata,
                    'uploadedAt' => date('Y-m-d H:i:s')
                ],
                'secureToken' => $this->generateSecureToken($file)
            ];
        } catch (\Exception $e) {
            error_log('Document Processing Error: ' . $e->getMessage());
            return null;
        }
    }

    private function validateUpload(array $file): void {
        // File size validation
        if ($file['size'] > self::MAX_FILE_SIZE) {
            throw new \Exception("File exceeds maximum size of 50MB");
        }

        // File type validation
        $finfo = new \finfo(FILEINFO_MIME_TYPE);
        $mimeType = $finfo->file($file['tmp_name']);

        if (!isset(self::ALLOWED_MIME_TYPES[$mimeType])) {
            throw new \Exception("Unsupported file type");
        }
    }

    private function extractText(array $file): string {
        $finfo = new \finfo(FILEINFO_MIME_TYPE);
        $mimeType = $finfo->file($file['tmp_name']);

        switch ($mimeType) {
            case 'application/pdf':
                $parser = new Parser();
                $pdf = $parser->parseFile($file['tmp_name']);
                return $pdf->getText();
            
            case 'text/plain':
                return file_get_contents($file['tmp_name']);
            
            default:
                throw new \Exception("Cannot extract text from this file type");
        }
    }

    private function generateMetadata(array $file, string $text): array {
        return [
            'fileSize' => $file['size'],
            'pageCount' => substr_count($text, "\n"),
            'extractionMethod' => $this->detectFileType($file)
        ];
    }

    private function detectFileType(array $file): string {
        $finfo = new \finfo(FILEINFO_MIME_TYPE);
        $mimeType = $finfo->file($file['tmp_name']);
        return self::ALLOWED_MIME_TYPES[$mimeType] ?? 'unknown';
    }

    private function generateSecureToken(array $file): string {
        // Ensure you have a secure secret key in a real application
        $secretKey = 'your_very_secret_key_that_should_be_stored_securely';
        
        $payload = [
            'filename' => $file['name'],
            'uploadTime' => time(),
            'exp' => time() + 3600 // Token expires in 1 hour
        ];

        return JWT::encode($payload, $secretKey, 'HS256');
    }
}
?>
