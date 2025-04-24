<?php
// GitHub webhook script
$secret = getenv('WEBHOOK_SECRET'); // Get secret from environment variable
$payload = file_get_contents('php://input');
$signature = $_SERVER['HTTP_X_HUB_SIGNATURE'] ?? '';

if ($signature) {
    $hash = "sha1=" . hash_hmac('sha1', $payload, $secret);
    if (hash_equals($hash, $signature)) {
        // Pull the latest changes
        $output = [];
        exec('cd /opt/massdevserver && git pull origin main 2>&1', $output);
        
        // Log the pull results
        file_put_contents('/opt/massdevserver/webhook.log', date('Y-m-d H:i:s') . " - Pull executed\n" . implode("\n", $output) . "\n\n", FILE_APPEND);
        
        http_response_code(200);
        echo "Pull executed successfully";
    } else {
        http_response_code(403);
        echo "Invalid signature";
    }
} else {
    http_response_code(401);
    echo "No signature";
}
