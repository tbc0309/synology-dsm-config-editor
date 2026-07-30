Ext.define('SYNO.SDS.EasyTier.Instance', {
	extend: 'SYNO.SDS.AppInstance',
	appWindowName: 'SYNO.SDS.EasyTier.Main',
	constructor: function() {
		this.callParent(arguments);
	}
});

Ext.define('SYNO.SDS.EasyTier.Main', {
	extend: 'SYNO.SDS.AppWindow',
	appInstance: null,

	constructor: function(cfg) {
		this.appInstance = cfg.appInstance;
		var appId = 'SYNO.SDS.EasyTier.Instance';
		var locale = 'enu';
		var frameTitle = 'EasyTier';
		// DSM loads texts/<language>/strings for the application. Container
		// Manager uses the same _TT lookup; all fallbacks stay local and safe.
		try {
			locale = _TT(appId, 'locale', 'code') || locale;
			frameTitle = _TT(appId, 'app', 'displayname') || frameTitle;
		} catch (ignore) {}
		if (!/^[a-z]{3}$/.test(locale)) {
			locale = 'enu';
		}
		frameTitle = String(frameTitle).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

		var config = Ext.apply({
			resizable: true,
			maximizable: true,
			minimizable: true,
			width: 920,
			height: 700,
			minWidth: 720,
			minHeight: 520,
			layout: 'fit',
			items: [
				new Ext.BoxComponent({
					height: '100%',
					html: '<iframe title="' + frameTitle + '" src="/webman/3rdparty/EasyTier/gettoken.html?lang=' + encodeURIComponent(locale) + '" frameborder="0" width="100%" height="100%" style="display:block"></iframe>'
				})
			]
		}, cfg);

		this.callParent([config]);
	}
});
