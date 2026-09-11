(function() {
    'use strict';

    const FAKE_VENDOR = 'Google Inc. (NVIDIA)';
    const FAKE_RENDERER = 'ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)';

    function patchWebGL(targetProto) {
        if (!targetProto || !targetProto.getParameter) return;
        const origGetParameter = targetProto.getParameter;

        const patchedGetParameter = function(parameter) {
            // UNMASKED_VENDOR_WEBGL
            if (parameter === 37445) {
                return FAKE_VENDOR;
            }
            // UNMASKED_RENDERER_WEBGL
            if (parameter === 37446) {
                return FAKE_RENDERER;
            }
            return origGetParameter.apply(this, arguments);
        };

        // 隐藏 Hook 痕迹
        try {
            Object.defineProperty(patchedGetParameter, 'name', { value: 'getParameter' });
            patchedGetParameter.toString = function() {
                return 'function getParameter() { [native code] }';
            };
        } catch (e) {}

        targetProto.getParameter = patchedGetParameter;
    }

    try {
        if (typeof WebGLRenderingContext !== 'undefined') {
            patchWebGL(WebGLRenderingContext.prototype);
        }
        if (typeof WebGL2RenderingContext !== 'undefined') {
            patchWebGL(WebGL2RenderingContext.prototype);
        }
    } catch (err) {}
})();
