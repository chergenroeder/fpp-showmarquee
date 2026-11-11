<?php

/*
 * Plugin API endpoints for fpp-matrixcountdown.
 * FPP mounts these under /api/plugin/fpp-matrixcountdown/
 * and proxies them to the Python daemon on port 32330.
 *
 * Function name: hyphens removed from plugin name per FPP convention.
 */

define('FPPMC_DAEMON_BASE', 'http://localhost:32330/api/plugin/matrixcountdown/');

function getEndpointsfppmatrixcountdown() {
    return array(
        array('method' => 'GET',  'endpoint' => 'status',         'callback' => 'fppmatrixcountdownStatus'),
        array('method' => 'GET',  'endpoint' => 'config',         'callback' => 'fppmatrixcountdownGetConfig'),
        array('method' => 'POST', 'endpoint' => 'config',         'callback' => 'fppmatrixcountdownPostConfig'),
        array('method' => 'POST', 'endpoint' => 'reload',         'callback' => 'fppmatrixcountdownReload'),
        array('method' => 'POST', 'endpoint' => 'preview',        'callback' => 'fppmatrixcountdownPreview'),
        array('method' => 'POST', 'endpoint' => 'state',          'callback' => 'fppmatrixcountdownState'),
        array('method' => 'POST', 'endpoint' => 'target',         'callback' => 'fppmatrixcountdownTarget'),
        array('method' => 'GET',  'endpoint' => 'models',         'callback' => 'fppmatrixcountdownModels'),
        array('method' => 'GET',  'endpoint' => 'fonts',          'callback' => 'fppmatrixcountdownFonts'),
        array('method' => 'GET',  'endpoint' => 'version',        'callback' => 'fppmatrixcountdownVersion'),
        array('method' => 'POST', 'endpoint' => 'daemon/start',   'callback' => 'fppmatrixcountdownDaemonStart'),
        array('method' => 'POST', 'endpoint' => 'daemon/stop',    'callback' => 'fppmatrixcountdownDaemonStop'),
        array('method' => 'POST', 'endpoint' => 'daemon/restart', 'callback' => 'fppmatrixcountdownDaemonRestart'),
    );
}

function fppmatrixcountdownDaemonRequest($path, $method = 'GET') {
    $opts = array(
        'http' => array(
            'method'        => $method,
            'timeout'       => 5,
            'ignore_errors' => true,
        )
    );
    if ($method === 'POST') {
        $body = file_get_contents('php://input');
        if ($body !== false && $body !== '') {
            $opts['http']['header']  = "Content-Type: application/json\r\n";
            $opts['http']['content'] = $body;
        }
    }
    $ctx  = stream_context_create($opts);
    $resp = @file_get_contents(FPPMC_DAEMON_BASE . $path, false, $ctx);
    if ($resp === false) {
        return json(array('error' => 'matrixcountdown daemon not running'));
    }
    $data = json_decode($resp, true);
    if ($data === null) {
        return json(array('error' => 'invalid response from daemon'));
    }
    return json($data);
}

function fppmatrixcountdownStatus()        { return fppmatrixcountdownDaemonRequest('status'); }
function fppmatrixcountdownGetConfig()     { return fppmatrixcountdownDaemonRequest('config'); }
function fppmatrixcountdownPostConfig()    { return fppmatrixcountdownDaemonRequest('config', 'POST'); }
function fppmatrixcountdownReload()        { return fppmatrixcountdownDaemonRequest('reload', 'POST'); }
function fppmatrixcountdownPreview()       { return fppmatrixcountdownDaemonRequest('preview', 'POST'); }
function fppmatrixcountdownState()         { return fppmatrixcountdownDaemonRequest('state', 'POST'); }
function fppmatrixcountdownTarget()        { return fppmatrixcountdownDaemonRequest('target', 'POST'); }
function fppmatrixcountdownModels()        { return fppmatrixcountdownDaemonRequest('models'); }
function fppmatrixcountdownFonts()         { return fppmatrixcountdownDaemonRequest('fonts'); }
function fppmatrixcountdownVersion()       { return fppmatrixcountdownDaemonRequest('version'); }
function fppmatrixcountdownDaemonStop()    { return fppmatrixcountdownDaemonRequest('daemon/stop', 'POST'); }
function fppmatrixcountdownDaemonRestart() { return fppmatrixcountdownDaemonRequest('daemon/restart', 'POST'); }

function fppmatrixcountdownDaemonStart() {
    global $settings;
    $plugin_dir = $settings['pluginDirectory'] . '/fpp-matrixcountdown';
    $daemon     = $plugin_dir . '/matrixcountdown.py';
    $alive = @file_get_contents(FPPMC_DAEMON_BASE . 'status');
    if ($alive !== false) {
        return json(array('status' => 'already_running'));
    }
    // The daemon must run as root to write the overlay buffer fppd (root)
    // creates with mode 0644. The web server runs as fpp, which FPP gives
    // passwordless sudo; -n fails instead of prompting if that's not so.
    // Its output goes nowhere: the daemon writes its own log (and logs its own
    // crashes) through a handler that follows FPP's log rotation.
    $sudo  = (function_exists('posix_geteuid') && posix_geteuid() === 0) ? '' : 'sudo -n ';
    $inner = 'MEDIADIR=' . escapeshellarg($settings['mediaDirectory']) .
             ' LOGDIR=' . escapeshellarg($settings['logDirectory']) .
             ' exec python3 ' . escapeshellarg($daemon) .
             ' >/dev/null 2>&1 </dev/null';
    shell_exec('nohup ' . $sudo . 'sh -c ' . escapeshellarg($inner) . ' >/dev/null 2>&1 &');
    usleep(1200000); // 1.2 s startup grace
    $alive = @file_get_contents(FPPMC_DAEMON_BASE . 'status');
    return json(array('status' => $alive !== false ? 'running' : 'starting'));
}

?>
