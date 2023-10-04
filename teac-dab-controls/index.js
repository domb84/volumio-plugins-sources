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
    // Optional, use if you need it
    var defer=libQ.defer();

	try {
		this.teacdabcontrolsServiceCmds('restart');
        this.pigpiodServiceCmds('restart');
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

            uiconf.sections[0].content[0].value = self.config.get('buttons_clk');
            uiconf.sections[0].content[1].value = self.config.get('buttons_miso');
            uiconf.sections[0].content[2].value = self.config.get('buttons_mosi');
            uiconf.sections[0].content[3].value = self.config.get('buttons_cs');
            uiconf.sections[0].content[4].value = self.config.get('buttons_channel1');
            uiconf.sections[0].content[5].value = self.config.get('buttons_channel2');

            defer.resolve(uiconf);
        })
        .fail(function () {
            self.logger.error('AutoStart - Failed to parse UI Configuration page: ' + error);
            defer.reject(new Error());
        });

    return defer.promise;
};

teacdabcontrols.prototype.getConfigurationFiles = function() {
	return ['config.json'];
}

teacdabcontrols.prototype.setUIConfig = function(data) {
	var self = this;
    
	//Perform your installation tasks here
    var uiconf = fs.readJsonSync(__dirname + '/UIConfig.json');

    return libQ.resolve();

};

teacdabcontrols.prototype.getConf = function(varName) {
	var self = this;
	//Perform your installation tasks here
    self.config = new (require('v-conf'))();
    self.config.loadFile(configFile);

};

teacdabcontrols.prototype.setConf = function(varName, varValue) {
	var self = this;
	//Perform your installation tasks here
    fs.writeJsonSync(self.configFile, JSON.stringify(conf));
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
