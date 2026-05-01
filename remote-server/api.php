<?php
/**
 * Homelab Control – All-Inkl API
 * Einzige Funktion: Wake-on-LAN
 * Alles andere läuft auf dem Mini-PC
 */

declare(strict_types=1);
ini_set('display_errors', '0');

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

// ── Request ───────────────────────────────────────────────────────────────────
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path   = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
$path   = rtrim($path, '/') ?: '/';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
if ($method === 'OPTIONS') { http_response_code(204); exit; }

function jsonOut(mixed $data, int $status = 200): never {
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

// ── Audit Log ─────────────────────────────────────────────────────────────────
function auditLog(string $event, string $extra = ''): void {
    $logDir = $GLOBALS['BASE'] . '/logs';
    if (!is_dir($logDir)) mkdir($logDir, 0750, true);
    $entry = json_encode([
        'ts'    => date('c'),
        'event' => $event,
        'ip'    => $_SERVER['REMOTE_ADDR'] ?? '',
        'extra' => $extra,
    ]);
    file_put_contents($logDir . '/wol.log', $entry . "\n", FILE_APPEND | LOCK_EX);
}

// ── Wake-on-LAN ───────────────────────────────────────────────────────────────
function wakeOnLan(string $mac): array {
    $clean = strtoupper(str_replace([':', '-'], '', $mac));
    if (strlen($clean) !== 12 || !ctype_xdigit($clean)) {
        return ['success' => false, 'error' => 'Ungültige MAC'];
    }
    $magic = str_repeat("\xff", 6) . str_repeat(pack('H*', $clean), 16);
    $sock  = socket_create(AF_INET, SOCK_DGRAM, SOL_UDP);
    if (!$sock) return ['success' => false, 'error' => 'Socket-Fehler'];
    socket_set_option($sock, SOL_SOCKET, SO_BROADCAST, 1);
    $ok = socket_sendto($sock, $magic, strlen($magic), 0, '255.255.255.255', 9);
    socket_close($sock);
    return $ok !== false
        ? ['success' => true, 'mac' => $mac]
        : ['success' => false, 'error' => 'Senden fehlgeschlagen'];
}

// ── Services aus .env ─────────────────────────────────────────────────────────
// MAC-Adressen direkt in .env: MINI_PC_MAC, LLM_SERVER_MAC (Bindestriche → Unterstriche)
function getMac(string $name): ?string {
    $key = strtoupper(str_replace('-', '_', $name)) . '_MAC';
    $val = $GLOBALS['env'][$key] ?? '';
    return $val !== '' ? $val : null;
}

// ── Router ────────────────────────────────────────────────────────────────────

// Health
if ($path === '/health' || $path === '/api/health') {
    jsonOut(['status' => 'ok', 'role' => 'allinkl', 'time' => date('c')]);
}

// WoL: POST /api/wol/{name}
if (preg_match('#^/api/wol/(.+)$#', $path, $m) && $method === 'POST') {
    $name = strtolower(trim($m[1]));
    $mac  = getMac($name);

    if (!$mac) {
        // Fallback: MAC direkt im Body mitschicken
        $body = json_decode(file_get_contents('php://input'), true);
        $mac  = $body['mac'] ?? null;
    }

    if (!$mac) {
        jsonOut(['error' => "Keine MAC für '$name' gefunden"], 404);
    }

    $result = wakeOnLan($mac);
    auditLog('WOL_' . strtoupper($name), $mac);
    jsonOut(['service' => $name, 'result' => $result]);
}

// Alles andere → 404 mit Hinweis
jsonOut([
    'error' => 'Dieser Endpunkt liegt auf dem Mini-PC',
    'hint'  => 'Nur /api/wol/* ist auf All-Inkl verfügbar',
], 404);
