'use strict';

var libQ = require('kew');
var fs = require('fs-extra');
var config = new (require('v-conf'))();
var exec = require('child_process').exec;
var execSync = require('child_process').execSync;


module.exports = teacdabcontrols;
function teacdabcontrols(context) {
	var self = this;

	this.context = context;
	this.commandRouter = this.context.coreCommand;
	this.logger = this.context.logger;
	this.configManager = this.context.configManager;
}



teacdabcontrols.prototype.onVolumioStart = function()
{
	var self = this;
	var configFile=this.commandRouter.pluginManager.getConfigurationFile(this.context,'config.json');
	this.config = new (require('v-conf'))();
	this.config.loadFile(configFile);

    return libQ.resolve();
}

teacdabcontrols.prototype.onStart = function() {
    var self = this;
	var defer=libQ.defer();

	try {
        this.pigpiodServiceCmds('start');
		this.teacdabcontrolsServiceCmds('start');
    } catch (e) {
        const err = 'Error starting Teac DAB controls';
        self.logger.error(err, e);
    }

	// Once the Plugin has successfull started resolve the promise
	defer.resolve();

    return defer.promise;
};

teacdabcontrols.prototype.onStop = function() {
    var self = this;
    var defer=libQ.defer();

	try {
		this.teacdabcontrolsServiceCmds('stop');
        this.pigpiodServiceCmds('stop');
    } catch (e) {
        const err = 'Error stopping Teac DAB controls';
        self.logger.error(err, e);
    }

    // Once the Plugin has successfull stopped resolve the promise
    defer.resolve();

    return libQ.resolve();
};

teacdabcontrols.prototype.onRestart = function() {
    var self = this;
    var defer=libQ.defer();

	try {
        this.pigpiodServiceCmds('restart');
		this.teacdabcontrolsServiceCmds('restart');
    } catch (e) {
        const err = 'Error restarting Teac DAB controls';
        self.logger.error(err, e);
    }

    // Once the Plugin has successfull stopped resolve the promise
    defer.resolve();

    return libQ.resolve();
};


// Configuration Methods -----------------------------------------------------------------------------

teacdabcontrols.prototype.getUIConfig = function() {
    const self = this;
    const defer = libQ.defer();

    this.logger.info('Teac DAB Controls - getUIConfig');

    const lang_code = this.commandRouter.sharedVars.get('language_code');

    this.commandRouter.i18nJson(__dirname + '/i18n/strings_' + lang_code + '.json',
        __dirname + '/i18n/strings_en.json',
        __dirname + '/UIConfig.json')
        .then(function (uiconf) {
            uiconf.sections[0].content[0].value = self.config.get('spi');
            uiconf.sections[0].content[1].value = self.config.get('spi_bus');
            uiconf.sections[0].content[2].value = self.config.get('buttons_clk');
            uiconf.sections[0].content[3].value = self.config.get('buttons_miso');
            uiconf.sections[0].content[4].value = self.config.get('buttons_mosi');
            uiconf.sections[0].content[5].value = self.config.get('buttons_cs');
            uiconf.sections[0].content[6].value = self.config.get('buttons_channel1');
            uiconf.sections[0].content[7].value = self.config.get('buttons_channel2');
            uiconf.sections[0].content[8].value = self.config.get('button_poll_rate');
            uiconf.sections[0].content[9].value = self.config.get('button_debounce_rate');
            uiconf.sections[0].content[10].value = self.config.get('button_cooldown_rate');
            // sections[1].content[0] is the "Edit values manually" toggle
            uiconf.sections[1].content[1].value = self.config.get('btn_enter');
            uiconf.sections[1].content[2].value = self.config.get('btn_radio');
            uiconf.sections[1].content[3].value = self.config.get('btn_spotify');
            uiconf.sections[1].content[4].value = self.config.get('btn_stop');
            uiconf.sections[1].content[5].value = self.config.get('btn_info');
            uiconf.sections[1].content[6].value = self.config.get('btn_favourite');
            uiconf.sections[1].content[7].value = self.config.get('btn_main_menu');
            uiconf.sections[1].content[8].value = self.config.get('btn_back');
            uiconf.sections[1].content[9].value = self.config.get('btn_no_press_channel1');
            uiconf.sections[1].content[10].value = self.config.get('btn_no_press_channel2');
            // sections[2] is "Configure Buttons (Capture)" — action buttons, no stored values
            uiconf.sections[3].content[0].value = self.config.get('rot_enc_A');
            uiconf.sections[3].content[1].value = self.config.get('rot_enc_B');
            uiconf.sections[4].content[0].value = self.config.get('lcd_rs');
            uiconf.sections[4].content[1].value = self.config.get('lcd_e');
            uiconf.sections[4].content[2].value = self.config.get('lcd_d4');
            uiconf.sections[4].content[3].value = self.config.get('lcd_d5');
            uiconf.sections[4].content[4].value = self.config.get('lcd_d6');
            uiconf.sections[4].content[5].value = self.config.get('lcd_d7');
            defer.resolve(uiconf);
        })
        .fail(function () {
            self.logger.error('Teac DAB Controls - Failed to parse UI Configuration page:' + error);
            defer.reject(new Error());
        });

    return defer.promise;
};

teacdabcontrols.prototype.saveOptions = function (data) {
    const self = this;

    // Function to check if a value is numeric, boolean, or comma-separated numbers
    function isValid(value) {
        // Check if the value is a boolean
        if (typeof value === 'boolean') {
            return true;
        }
        
        // Check if the value is a comma-separated list of numbers
        if (typeof value === 'string' && value.match(/^\s*(\d+\s*,\s*)*\d+\s*$/)) {
            return true;
        }
        
        // Check if the value is a single numeric value
        return !isNaN(parseFloat(value)) && isFinite(value);
    }

    self.logger.info('Teac DAB Controls - saving settings');

    const formattedJsonString = JSON.stringify(data, null, 2);
    // console.log(formattedJsonString);

    // Parse JSON string into a JavaScript object
    const jsonObject = JSON.parse(formattedJsonString);

    // Iterate through the object and save if the item is valid
    for (const key in jsonObject) {
        if (jsonObject.hasOwnProperty(key)) {
            const value = jsonObject[key];
            // console.log(`${key}: ${value}`);
            if (isValid(value)) {
                // console.log(`${value} is a valid number, comma seperated numbers or boolean. Saving ${key}.`);
                self.config.set(key, value);
            } else {
                self.logger.error(`${value} is not a valid number, comma seperated numbers or boolean. Not saving ${key}.`);
                this.commandRouter.pushToastMessage('fail', ("Teac DAB Controls"), (`${value} is not a valid number, comma seperated numbers or boolean. Not saving ${key}.`));
            }
        }
    }
    
    this.commandRouter.pushToastMessage('success', ("Teac DAB Controls"), this.commandRouter.getI18nString("COMMON.CONFIGURATION_UPDATE_DESCRIPTION"));

    self.logger.info('Teac DAB Controls - settings saved');
    self.logger.info('Teac DAB Controls - restarting services');
    self.onRestart()

    return libQ.resolve();
};


teacdabcontrols.prototype.getConfigurationFiles = function() {
	return ['config.json'];
}

// Button capture ("learn") -------------------------------------------------

var CAPTURE_FLAG_PATH = '/tmp/teac-dab-controls-capture-on';
var CAPTURE_READING_PATH = '/tmp/teac-dab-controls-capture.json';
var CAPTURE_TIMEOUT_MS = 30000;
var CAPTURE_POLL_MS = 200;

// config key -> friendly label shown in toasts
var CAPTURE_LABELS = {
    btn_enter: 'Enter',
    btn_radio: 'Radio',
    btn_spotify: 'Spotify',
    btn_stop: 'Stop',
    btn_info: 'Info',
    btn_favourite: 'Favourite',
    btn_main_menu: 'Main Menu',
    btn_back: 'Back'
};

// One entry point per button (UIConfig button onClick targets these by name)
teacdabcontrols.prototype.captureBtnEnter = function () { return this.startCapture('btn_enter'); };
teacdabcontrols.prototype.captureBtnRadio = function () { return this.startCapture('btn_radio'); };
teacdabcontrols.prototype.captureBtnSpotify = function () { return this.startCapture('btn_spotify'); };
teacdabcontrols.prototype.captureBtnStop = function () { return this.startCapture('btn_stop'); };
teacdabcontrols.prototype.captureBtnInfo = function () { return this.startCapture('btn_info'); };
teacdabcontrols.prototype.captureBtnFavourite = function () { return this.startCapture('btn_favourite'); };
teacdabcontrols.prototype.captureBtnMainMenu = function () { return this.startCapture('btn_main_menu'); };
teacdabcontrols.prototype.captureBtnBack = function () { return this.startCapture('btn_back'); };

teacdabcontrols.prototype.startCapture = function (targetKey) {
    const self = this;
    const label = CAPTURE_LABELS[targetKey] || targetKey;

    // Cancel anything already running and clear stale readings.
    self.stopCapture();

    try {
        fs.writeFileSync(CAPTURE_FLAG_PATH, '');
    } catch (e) {
        self.logger.error('Teac DAB Controls - could not start capture: ' + e);
        self.commandRouter.pushToastMessage('error', 'Button Capture', 'Could not start capture mode.');
        return libQ.resolve();
    }

    self._capture = {
        target: targetKey,
        label: label,
        candidate: null,    // { channel, value } awaiting confirmation
        lastSeq: null,
        deadline: Date.now() + CAPTURE_TIMEOUT_MS
    };

    self.commandRouter.pushToastMessage('info', 'Button Capture',
        'Press the "' + label + '" button on the unit...');

    self._captureTimer = setInterval(function () { self.pollCapture(); }, CAPTURE_POLL_MS);
    return libQ.resolve();
};

teacdabcontrols.prototype.pollCapture = function () {
    const self = this;
    const cap = self._capture;
    if (!cap) { self.stopCapture(); return; }

    if (Date.now() > cap.deadline) {
        self.commandRouter.pushToastMessage('warning', 'Button Capture',
            'Timed out configuring "' + cap.label + '". Nothing was saved.');
        self.stopCapture();
        return;
    }

    let reading;
    try {
        if (!fs.existsSync(CAPTURE_READING_PATH)) { return; }
        reading = fs.readJsonSync(CAPTURE_READING_PATH);
    } catch (e) {
        return;  // partial write; try again next tick
    }

    if (reading == null || reading.seq == null) { return; }
    if (reading.seq === cap.lastSeq) { return; }   // no new press since last poll
    cap.lastSeq = reading.seq;

    // Each new seq is one detected physical press (Python already filters out
    // the resting value and key-release).
    const ch = reading.channel;
    const val = reading.value;

    if (cap.candidate == null) {
        cap.candidate = { channel: ch, value: val };
        self.commandRouter.pushToastMessage('info', 'Button Capture',
            'Read channel ' + ch + ', value ' + val + '. Press "' + cap.label + '" again to confirm.');
        return;
    }

    if (cap.candidate.channel === ch && cap.candidate.value === val) {
        const configValue = ch + ', ' + val;
        self.config.set(cap.target, configValue);
        if (!self._capturedValues) { self._capturedValues = {}; }
        self._capturedValues[cap.label] = configValue;
        self.commandRouter.pushToastMessage('success', 'Button Capture',
            '"' + cap.label + '" set to ' + configValue + '. Configure more, then click "Save & Restart Controls" when done.');
        self.stopCapture();
    } else {
        cap.candidate = { channel: ch, value: val };
        self.commandRouter.pushToastMessage('info', 'Button Capture',
            'Got a different value (channel ' + ch + ', value ' + val + '). Press "' + cap.label + '" again to confirm.');
    }
};

teacdabcontrols.prototype.stopCapture = function () {
    const self = this;
    if (self._captureTimer) {
        clearInterval(self._captureTimer);
        self._captureTimer = null;
    }
    self._capture = null;
    try { fs.removeSync(CAPTURE_FLAG_PATH); } catch (e) {}
    try { fs.removeSync(CAPTURE_READING_PATH); } catch (e) {}
};

// Apply everything captured this session and restart the controls once.
teacdabcontrols.prototype.saveCapture = function () {
    const self = this;

    self.stopCapture();   // cancel any capture still in progress

    const captured = self._capturedValues || {};
    const labels = Object.keys(captured);

    if (labels.length === 0) {
        self.commandRouter.pushToastMessage('info', 'Button Capture',
            'No new button captures to save.');
        return libQ.resolve();
    }

    const summary = labels.map(function (label) { return label + ' = ' + captured[label]; }).join(', ');
    self.commandRouter.pushToastMessage('success', 'Button Capture',
        'Saved (' + summary + '). Restarting controls...');

    self._capturedValues = {};
    self.onRestart();
    return libQ.resolve();
};

// Plugin methods -----------------------------------------------------------------------------

teacdabcontrols.prototype.teacdabcontrolsServiceCmds = function (cmd) {
    var self = this;

    if (!['start', 'stop', 'restart'].includes(cmd)) {
        throw TypeError('Unknown systemd command: ', cmd);
    }
    const { stdout, stderr } = execSync(`/usr/bin/sudo /bin/systemctl ${cmd} teac-dab-controls.service -q`, { uid: 1000, gid: 1000 });
    if (stderr) {
        self.logger.error(`Unable to ${cmd} Daemon: `, stderr);
    } else if (stdout) { }
    self.logger.info(`Teac DAB controls Daemon service ${cmd}ed!`);
};

teacdabcontrols.prototype.pigpiodServiceCmds = function (cmd) {
    var self = this;

    if (!['start', 'stop', 'restart'].includes(cmd)) {
        throw TypeError('Unknown systemd command: ', cmd);
    }
    const { stdout, stderr } = execSync(`/usr/bin/sudo /bin/systemctl ${cmd} pigpiod.service -q`, { uid: 1000, gid: 1000 });
    if (stderr) {
        self.logger.error(`Unable to ${cmd} Daemon: `, stderr);
    } else if (stdout) { }
    self.logger.info(`pigpio Daemon service ${cmd}ed!`);
};
