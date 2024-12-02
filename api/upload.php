<?php
// Strict error handling
ini_set('display_errors', 0);
ini_set('log_errors', 1);
error_reporting(E_ALL);

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Determine project root
$projectRoot = realpath(dirname(__DIR__));

// Try multiple potential autoload paths
$autoloadPaths = [
    $projectRoot . '/vendor/autoload.php',
    $projectRoot . '/autoload.php',
    __DIR__ . '/../vendor/autoload.php'
];

$autoloaded = false;
foreach ($autoloadPaths as $path) {
    if (file_exists($path)) {
        require_once $path;
        $autoloaded = true;
        break;
    }
}

if (!$autoloaded) {
    error_log('Autoload file not found. Checked paths: ' . implode(', ', $autoloadPaths));
    
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error' => 'Composer autoload not found. Please run "composer install"'
    ]);
    exit;
}

try {
    // Validate request method
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        throw new Exception('Invalid request method');
    }

    // Check if file was uploaded
    if (empty($_FILES['document'])) {
        throw new Exception('No file uploaded');
    }

    // Process the file
    $processor = new PDFTextExtractor\DocumentProcessor();
    $result = $processor->processUpload($_FILES['document']);

    if ($result === null) {
        throw new Exception('Document processing failed');
    }

    // Send successful response
    echo json_encode([
        'success' => true,
        'document' => $result['document'],
        'token' => $result['secureToken']
    ]);

} catch (Exception $e) {
    // Log the error
    error_log('Upload Error: ' . $e->getMessage());

    // Send error response
    http_response_code(400);
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage()
    ]);
}
exit;
?>