<?php
/**
 * Homelab Control – Mini-PC API
 * Läuft lokal auf dem Mini-PC, erreichbar per Tailscale
 * Endpunkte: /health, /api/status, /api/metrics, /api/gpu, /api/audit
 */

declare(strict_types=1);
ini_set('display_errors', '0');
error_reporting(E_ALL);

$BASE = __DIR__;

// ── .env laden ────────────────────────────────────────────────────────────────
$env = [];
if (file_exists($BASE . '/.env')) {
    foreach (file($BASE . '/.env', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) continue;
        [$k, $v] = explode('=', $line, 2);
        $env[trim($k)] = trim($v);
    }
}
function env(string $key, string $default = ''): string {
    return $GLOBALS['env'][$key] ?? $default;
}

// ── Request ───────────────────────────────────────────────────────────────────
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path   = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
$path   = rtrim($path, '/') ?: '/';
$ip     = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';

// ── CORS – erlaubt homelab-control.com + localhost ────────────────────────────
$allowed_origins = [
    'https://homelab-control.com',
    'https://www.homelab-control.com',
    'http://localhost:8000',
    'http://localhost',
];
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if (in_array($origin, $allowed_origins, true)) {
    header("Access-Control-Allow-Origin: $origin");
} else {
    header('Access-Control-Allow-Origin: https://homelab-control.com');
}
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-Api-Token');
header('Access-Control-Allow-Credentials: true');
if ($method === 'OPTIONS') { http_response_code(204); exit; }

// ── Token-Schutz (aktiv wenn LOCAL_API_TOKEN gesetzt) ─────────────────────────
$requiredToken = env('LOCAL_API_TOKEN');
if ($requiredToken !== '') {
    $provided = $_SERVER['HTTP_X_API_TOKEN'] ?? '';
    if (!hash_equals($requiredToken, $provided)) {
        http_response_code(401);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['error' => 'Unauthorized']);
        exit;
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function jsonOut(mixed $data, int $status = 200): never {
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-cache');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function auditLog(string $event, string $ip, string $path, array $extra = []): void {
    $logDir = $GLOBALS['BASE'] . '/logs';
    if (!is_dir($logDir)) mkdir($logDir, 0750, true);
    $entry = array_merge(['ts' => date('c'), 'event' => $event, 'ip' => $ip, 'path' => $path], $extra);
    file_put_contents($logDir . '/audit.log', json_encode($entry) . "\n", FILE_APPEND | LOCK_EX);
}

// ── Services laden ────────────────────────────────────────────────────────────
function loadServices(): array {
    $file = $GLOBALS['BASE'] . '/services/services.json';
    if (!file_exists($file)) return [];
    return json_decode(file_get_contents($file), true) ?? [];
}

// ── HTTP-Check ────────────────────────────────────────────────────────────────
function checkService(string $name, array $cfg): array {
    // Self-check: if this is the local machine, the API running means it's up
    if (!empty($cfg['self'])) {
        return [
            'name'       => $name,
            'label'      => $cfg['label'] ?? $name,
            'url'        => $cfg['url'] ?? null,
            'status'     => 'up',
            'latency_ms' => 0,
            'icon'       => $cfg['icon'] ?? 'server',
            'tags'       => $cfg['tags'] ?? [],
            'wol'        => isset($cfg['mac']) && $cfg['mac'] !== '',
            'shutdown'   => !empty($cfg['shutdown']),
        ];
    }

    $url    = $cfg['health_url'] ?? $cfg['url'] ?? null;
    $status = 'unknown';
    $latency = null;

    if ($url) {
        $t0  = microtime(true);
        $ctx = stream_context_create(['http' => ['timeout' => 5, 'ignore_errors' => true]]);
        $res = @file_get_contents($url, false, $ctx);
        $latency = (int) round((microtime(true) - $t0) * 1000);

        if ($res !== false) {
            preg_match('/HTTP\/\S+ (\d+)/', $http_response_header[0] ?? '', $m);
            $code   = (int)($m[1] ?? 0);
            $status = ($code > 0 && $code < 400) ? 'up' : 'degraded';
        } else {
            $status = 'down';
        }
    }

    return [
        'name'       => $name,
        'label'      => $cfg['label'] ?? $name,
        'url'        => $cfg['url'] ?? null,
        'status'     => $status,
        'latency_ms' => $latency,
        'icon'       => $cfg['icon'] ?? 'server',
        'tags'       => $cfg['tags'] ?? [],
        'wol'        => isset($cfg['mac']) && $cfg['mac'] !== '',
        'shutdown'   => !empty($cfg['shutdown']),
    ];
}

// ── Prometheus ────────────────────────────────────────────────────────────────
function fetchMetrics(): array {
    $results = [];
    foreach ($GLOBALS['env'] as $key => $val) {
        if (!str_ends_with($key, '_NODE_EXPORTER')) continue;
        $name = strtolower(str_replace('_NODE_EXPORTER', '', $key));
        $url  = 'http://' . $val . '/metrics';
        $ctx  = stream_context_create(['http' => ['timeout' => 5, 'ignore_errors' => true]]);
        $raw  = @file_get_contents($url, false, $ctx);
        $results[] = $raw !== false
            ? ['host' => $name, 'metrics' => parsePrometheus($raw), 'status' => 'ok']
            : ['host' => $name, 'metrics' => [], 'status' => 'error'];
    }
    return $results;
}

function fetchGpuMetrics(): array {
    $endpoint = env('LLM_GPU_EXPORTER');
    if (!$endpoint) return [];
    $url = 'http://' . $endpoint . '/metrics';
    $ctx = stream_context_create(['http' => ['timeout' => 5, 'ignore_errors' => true]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) return [['source' => $endpoint, 'metrics' => [], 'status' => 'error']];
    $all = parsePrometheus($raw);
    $gpu = array_filter($all, fn($k) => preg_match('/gpu|memory|temperature|utilization|power/i', $k), ARRAY_FILTER_USE_KEY);
    return [['source' => $endpoint, 'metrics' => $gpu, 'status' => 'ok']];
}

function parsePrometheus(string $text): array {
    $result = [];
    foreach (explode("\n", $text) as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#') continue;
        $parts = explode(' ', $line);
        if (count($parts) < 2) continue;
        $key = preg_replace('/\{.*?\}/', '', $parts[0]);
        $result[$key] = (float) end($parts);
    }
    return $result;
}

// ── Router ────────────────────────────────────────────────────────────────────

if ($path === '/health' || $path === '/api/health') {
    jsonOut(['status' => 'ok', 'role' => 'minipc', 'time' => date('c')]);
}

if ($path === '/api/status' && $method === 'GET') {
    $services = loadServices();
    $result = [];
    foreach ($services as $name => $cfg) {
        $result[] = checkService($name, $cfg);
    }
    auditLog('STATUS', $ip, $path);
    jsonOut(['services' => $result, 'checked_at' => date('c')]);
}

if ($path === '/api/services' && $method === 'GET') {
    jsonOut(['services' => loadServices()]);
}

if ($path === '/api/metrics' && $method === 'GET') {
    jsonOut(['metrics' => fetchMetrics(), 'timestamp' => date('c')]);
}

if ($path === '/api/gpu' && $method === 'GET') {
    jsonOut(['gpu' => fetchGpuMetrics(), 'timestamp' => date('c')]);
}

if ($path === '/api/audit' && $method === 'GET') {
    $limit   = min((int)($_GET['limit'] ?? 50), 200);
    $logFile = $BASE . '/logs/audit.log';
    $entries = [];
    if (file_exists($logFile)) {
        $lines = array_filter(explode("\n", file_get_contents($logFile)));
        $lines = array_slice(array_reverse(array_values($lines)), 0, $limit);
        foreach ($lines as $line) {
            $d = json_decode($line, true);
            if ($d) $entries[] = $d;
        }
    }
    jsonOut(['entries' => $entries, 'total' => count($entries)]);
}

// POST /api/shutdown/{name}
if (preg_match('#^/api/shutdown/(.+)$#', $path, $m) && $method === 'POST') {
    $name    = strtolower(trim($m[1]));
    $services = loadServices();
    $cfg     = $services[$name] ?? null;

    if (!$cfg || empty($cfg['shutdown'])) {
        jsonOut(['error' => "Shutdown nicht verfügbar für '$name'"], 404);
    }

    auditLog('SHUTDOWN', $ip, $path, ['service' => $name]);

    if (!empty($cfg['self'])) {
        exec('sudo /sbin/shutdown -h now > /dev/null 2>&1 &');
        jsonOut(['success' => true, 'service' => $name]);
    }

    $cmd = $cfg['shutdown_cmd'] ?? '';
    if ($cmd === '') {
        jsonOut(['error' => "shutdown_cmd nicht konfiguriert für '$name'"], 500);
    }

    exec($cmd . ' > /dev/null 2>&1 &');
    jsonOut(['success' => true, 'service' => $name]);
}

jsonOut(['error' => 'Route nicht gefunden: ' . $path], 404);
