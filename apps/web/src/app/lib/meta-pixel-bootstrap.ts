import { nonPublicTrackingRoutePrefixes } from "./public-tracking-policy";

function inlineJson(value: unknown) {
  return (JSON.stringify(value) ?? "null")
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

/**
 * Builds a small public-only bootstrap. It contains only the public Pixel ID
 * and static route policy; no seller data, secret, or request payload enters
 * the document.
 */
export function buildMetaPixelBootstrap(pixelId: string | undefined) {
  const normalizedPixelId = pixelId?.trim();
  if (!normalizedPixelId) return null;
  const pixelIdJson = inlineJson(normalizedPixelId);
  const excludedPrefixesJson = inlineJson([...nonPublicTrackingRoutePrefixes]);

  return `(function(w,d,p,x){var n=w.location.pathname||"/";var b=x.some(function(r){return n===r||n.indexOf(r+"/")===0;});if(b)return;var q=w.fbq;if(!q){q=function(){q.callMethod?q.callMethod.apply(q,arguments):q.queue.push(Array.prototype.slice.call(arguments));};q.queue=[];q.loaded=true;q.version="2.0";w.fbq=q;w._fbq=q;}var i=w.__stonegateMetaPixelIds||(w.__stonegateMetaPixelIds=[]);if(i.indexOf(p)<0){q("init",p);i.push(p);}if(w.__stonegateMetaLastPageViewPath!==n){w.__stonegateMetaLastPageViewPath=n;q("track","PageView");}var u="https://connect.facebook.net/en_US/fbevents.js";var s=d.getElementById("stonegate-meta-pixel-script")||d.querySelector('script[src="'+u+'"]');if(!s){s=d.createElement("script");s.id="stonegate-meta-pixel-script";s.async=true;s.src=u;s.addEventListener("load",function(){s.dataset.stonegateLoaded="true";},{once:true});(d.head||d.documentElement).appendChild(s);}})(window,document,${pixelIdJson},${excludedPrefixesJson});`;
}
