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
        array('method' => 'GET',  'endpoint' => 'models',         'callback' => 'fppmatrixcountdownModels'),
        array('method' => 'GET',  'endpoint' => 'fonts',          'callback' => 'fppmatrixcountdownFonts'),
        array('method' => 'GET',  'endpoint' => 'version',        'callback' => 'fppmatrixcountdownVersion'),
        array('method' => 'GET',  'endpoint' => 'daemon/start',   'callback' => 'fppmatrixcountdownDaemonStart'),
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
function fppmatrixcountdownModels()        { return fppmatrixcountdownDaemonRequest('models'); }
function fppmatrixcountdownFonts()         { return fppmatrixcountdownDaemonRequest('fonts'); }
function fppmatrixcountdownVersion()       { return fppmatrixcountdownDaemonRequest('version'); }
function fppmatrixcountdownDaemonStop()    { return fppmatrixcountdownDaemonRequest('daemon/stop', 'POST'); }
function fppmatrixcountdownDaemonRestart() { return fppmatrixcountdownDaemonRequest('daemon/restart', 'POST'); }

function fppmatrixcountdownDaemonStart() {
    global $settings;
    $plugin_dir = $settings['pluginDirectory'] . '/fpp-matrixcountdown';
    $daemon     = $plugin_dir . '/matrixcountdown.py';
    $logfile    = $settings['logDirectory'] . '/plugin-fpp-matrixcountdown.log';
    $alive = @file_get_contents(FPPMC_DAEMON_BASE . 'status');
    if ($alive !== false) {
        return json(array('status' => 'already_running'));
    }
    shell_exec('MEDIADIR=' . escapeshellarg($settings['mediaDirectory']) .
               ' LOGDIR=' . escapeshellarg($settings['logDirectory']) .
               ' nohup python3 ' . escapeshellarg($daemon) .
               ' >> ' . escapeshellarg($logfile) . ' 2>&1 </dev/null &');
    usleep(1200000); // 1.2 s startup grace
    $alive = @file_get_contents(FPPMC_DAEMON_BASE . 'status');
    return json(array('status' => $alive !== false ? 'running' : 'starting'));
}

?>
