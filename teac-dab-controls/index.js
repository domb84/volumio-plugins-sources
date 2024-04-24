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
            uiconf.sections[1].content[0].value = self.config.get('btn_enter');
            uiconf.sections[1].content[1].value = self.config.get('btn_radio');
            uiconf.sections[1].content[2].value = self.config.get('btn_spotify');
            uiconf.sections[1].content[3].value = self.config.get('btn_stop');
            uiconf.sections[1].content[4].value = self.config.get('btn_info');
            uiconf.sections[1].content[5].value = self.config.get('btn_favourite');
            uiconf.sections[1].content[6].value = self.config.get('btn_main_menu');
            uiconf.sections[1].content[7].value = self.config.get('btn_no_press_channel1');
            uiconf.sections[1].content[8].value = self.config.get('btn_no_press_channel2');
            uiconf.sections[2].content[0].value = self.config.get('rot_enc_A');
            uiconf.sections[2].content[1].value = self.config.get('rot_enc_B');
            uiconf.sections[3].content[0].value = self.config.get('lcd_rs');
            uiconf.sections[3].content[1].value = self.config.get('lcd_e');
            uiconf.sections[3].content[2].value = self.config.get('lcd_d4');
            uiconf.sections[3].content[3].value = self.config.get('lcd_d5');
            uiconf.sections[3].content[4].value = self.config.get('lcd_d6');
            uiconf.sections[3].content[5].value = self.config.get('lcd_d7');
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
