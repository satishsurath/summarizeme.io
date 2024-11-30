<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST');
header('Access-Control-Allow-Headers: Content-Type');

$uploadDir = './uploads/';
$response = ['status' => 'error', 'message' => 'Unknown error'];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (isset($_FILES['file'])) {
        $file = $_FILES['file'];
        $fileName = uniqid() . '_' . basename($file['name']);
        $uploadPath = $uploadDir . $fileName;

        // Basic file validation
        $allowedTypes = ['application/pdf'];
        $maxFileSize = 10 * 1024 * 1024; // 10MB

        if (in_array($file['type'], $allowedTypes) && $file['size'] <= $maxFileSize) {
            if (move_uploaded_file($file['tmp_name'], $uploadPath)) {
                $response = [
                    'status' => 'success', 
                    'message' => 'File uploaded successfully',
                    'fileName' => $fileName
                ];
            } else {
                $response['message'] = 'File upload failed';
            }
        } else {
            $response['message'] = 'Invalid file type or size';
        }
    }
}

echo json_encode($response);
exit;