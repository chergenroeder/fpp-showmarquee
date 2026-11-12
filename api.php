<?php

/*
 * Plugin API endpoints for fpp-showmarquee.
 * FPP mounts these under /api/plugin/fpp-showmarquee/
 * and proxies them to the Python daemon on port 32330.
 *
 * Function name: hyphens removed from plugin name per FPP convention.
 */

define('FPPMC_DAEMON_BASE', 'http://localhost:32330/api/plugin/showmarquee/');

function getEndpointsfppshowmarquee() {
    return array(
        array('method' => 'GET',  'endpoint' => 'status',         'callback' => 'fppshowmarqueeStatus'),
        array('method' => 'GET',  'endpoint' => 'config',         'callback' => 'fppshowmarqueeGetConfig'),
        array('method' => 'POST', 'endpoint' => 'config',         'callback' => 'fppshowmarqueePostConfig'),
        array('method' => 'POST', 'endpoint' => 'reload',         'callback' => 'fppshowmarqueeReload'),
        array('method' => 'POST', 'endpoint' => 'preview',        'callback' => 'fppshowmarqueePreview'),
        array('method' => 'POST', 'endpoint' => 'state',          'callback' => 'fppshowmarqueeState'),
        array('method' => 'POST', 'endpoint' => 'target',         'callback' => 'fppshowmarqueeTarget'),
        array('method' => 'GET',  'endpoint' => 'models',         'callback' => 'fppshowmarqueeModels'),
        array('method' => 'GET',  'endpoint' => 'fonts',          'callback' => 'fppshowmarqueeFonts'),
        array('method' => 'GET',  'endpoint' => 'version',        'callback' => 'fppshowmarqueeVersion'),
        array('method' => 'GET',  'endpoint' => 'logos',          'callback' => 'fppshowmarqueeLogos'),
        array('method' => 'GET',  'endpoint' => 'logo',           'callback' => 'fppshowmarqueeGetLogo'),
        array('method' => 'POST', 'endpoint' => 'logo',           'callback' => 'fppshowmarqueePostLogo'),
        array('method' => 'POST', 'endpoint' => 'logo/delete',    'callback' => 'fppshowmarqueeDeleteLogo'),
        array('method' => 'POST', 'endpoint' => 'daemon/start',   'callback' => 'fppshowmarqueeDaemonStart'),
        array('method' => 'POST', 'endpoint' => 'daemon/stop',    'callback' => 'fppshowmarqueeDaemonStop'),
        array('method' => 'POST', 'endpoint' => 'daemon/restart', 'callback' => 'fppshowmarqueeDaemonRestart'),
    );
}

function fppshowmarqueeDaemonRequest($path, $method = 'GET') {
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
        return json(array('error' => 'showmarquee daemon not running'));
    }
    $data = json_decode($resp, true);
    if ($data === null) {
        return json(array('error' => 'invalid response from daemon'));
    }
    return json($data);
}

function fppshowmarqueeStatus()        { return fppshowmarqueeDaemonRequest('status'); }
function fppshowmarqueeGetConfig()     { return fppshowmarqueeDaemonRequest('config'); }
function fppshowmarqueePostConfig()    { return fppshowmarqueeDaemonRequest('config', 'POST'); }
function fppshowmarqueeReload()        { return fppshowmarqueeDaemonRequest('reload', 'POST'); }
function fppshowmarqueePreview()       { return fppshowmarqueeDaemonRequest('preview', 'POST'); }
function fppshowmarqueeState()         { return fppshowmarqueeDaemonRequest('state', 'POST'); }
function fppshowmarqueeTarget()        { return fppshowmarqueeDaemonRequest('target', 'POST'); }
function fppshowmarqueeModels()        { return fppshowmarqueeDaemonRequest('models'); }
function fppshowmarqueeFonts()         { return fppshowmarqueeDaemonRequest('fonts'); }
function fppshowmarqueeVersion()       { return fppshowmarqueeDaemonRequest('version'); }
function fppshowmarqueeLogos()         { return fppshowmarqueeDaemonRequest('logos'); }
function fppshowmarqueeGetLogo()       { return fppshowmarqueeDaemonRequest('logo'); }
function fppshowmarqueePostLogo()      { return fppshowmarqueeDaemonRequest('logo', 'POST'); }
function fppshowmarqueeDeleteLogo()    { return fppshowmarqueeDaemonRequest('logo/delete', 'POST'); }
function fppshowmarqueeDaemonStop()    { return fppshowmarqueeDaemonRequest('daemon/stop', 'POST'); }
function fppshowmarqueeDaemonRestart() { return fppshowmarqueeDaemonRequest('daemon/restart', 'POST'); }

function fppshowmarqueeDaemonStart() {
    $alive = @file_get_contents(FPPMC_DAEMON_BASE . 'status');
    if ($alive !== false) {
        return json(array('status' => 'already_running'));
    }
    // The daemon must run as root to write the overlay buffer fppd (root)
    // creates. Rather than start it from the web server (which runs as fpp),
    // ask fppd to run the plugin's "Show Marquee - Start" command: fppd runs
    // command scripts as root, through FPP's own command API.
    $body = json_encode(array('command' => 'Show Marquee - Start', 'multisyncCommand' => false,
                              'multisyncHosts' => '', 'args' => array()));
    $ctx = stream_context_create(array('http' => array(
        'method' => 'POST', 'header' => "Content-Type: application/json\r\n",
        'content' => $body, 'timeout' => 5, 'ignore_errors' => true)));
    $sent = @file_get_contents('http://127.0.0.1/api/command', false, $ctx);
    if ($sent === false) {
        return json(array('status' => 'error', 'error' => "couldn't reach FPP's command API"));
    }
    usleep(1200000); // 1.2 s startup grace
    $alive = @file_get_contents(FPPMC_DAEMON_BASE . 'status');
    return json(array('status' => $alive !== false ? 'running' : 'starting'));
}

?>
