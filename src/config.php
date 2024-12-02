<?php
// src/config.php
define('UPLOAD_DIR', __DIR__ . '/../uploads/');
define('MAX_FILE_SIZE', 50 * 1024 * 1024); // 50MB
define('ALLOWED_EXTENSIONS', ['pdf', 'txt']);

// Generate a secure random JWT secret
$_ENV['JWT_SECRET'] = bin2hex(random_bytes(32));
?>