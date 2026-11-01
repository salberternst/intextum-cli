var ke=Object.defineProperty;var Te=(t,e)=>{for(var r in e)ke(t,r,{get:e[r],enumerable:!0})};var Qt={};Te(Qt,{AnnotationPictureClassification:()=>Q,AnnotationPictureDescription:()=>mt,DoclingAnnotationElement:()=>H,DoclingItemElement:()=>C,ImgPage:()=>E,ImgPages:()=>x,ImgTrace:()=>W,ItemCode:()=>ft,ItemKeyValue:()=>gt,ItemOverlay:()=>yt,ItemProvenance:()=>et,ItemTable:()=>_t,ItemTemplate:()=>Nt,ItemText:()=>vt,ItemTooltip:()=>bt,ItemView:()=>K,TablePage:()=>k,TablePages:()=>T,customDoclingAnnotationElement:()=>Rt,customDoclingItemElement:()=>tt,normalBbox:()=>z});var De=Object.defineProperty,Oe=Object.getOwnPropertyDescriptor,h=(t,e,r,i)=>{for(var s=i>1?void 0:i?Oe(e,r):e,a=t.length-1,o;a>=0;a--)(o=t[a])&&(s=(i?o(e,r,s):o(s))||s);return i&&s&&De(e,r,s),s},I=t=>(e,r)=>{r!==void 0?r.addInitializer((()=>{customElements.define(t,e)})):customElements.define(t,e)},Me=class{get shadowRoot(){return this.__host.__shadowRoot}constructor(e){this.ariaAtomic="",this.ariaAutoComplete="",this.ariaBrailleLabel="",this.ariaBrailleRoleDescription="",this.ariaBusy="",this.ariaChecked="",this.ariaColCount="",this.ariaColIndex="",this.ariaColSpan="",this.ariaCurrent="",this.ariaDescription="",this.ariaDisabled="",this.ariaExpanded="",this.ariaHasPopup="",this.ariaHidden="",this.ariaInvalid="",this.ariaKeyShortcuts="",this.ariaLabel="",this.ariaLevel="",this.ariaLive="",this.ariaModal="",this.ariaMultiLine="",this.ariaMultiSelectable="",this.ariaOrientation="",this.ariaPlaceholder="",this.ariaPosInSet="",this.ariaPressed="",this.ariaReadOnly="",this.ariaRequired="",this.ariaRoleDescription="",this.ariaRowCount="",this.ariaRowIndex="",this.ariaRowSpan="",this.ariaSelected="",this.ariaSetSize="",this.ariaSort="",this.ariaValueMax="",this.ariaValueMin="",this.ariaValueNow="",this.ariaValueText="",this.role="",this.form=null,this.labels=[],this.states=new Set,this.validationMessage="",this.validity={},this.willValidate=!0,this.__host=e}checkValidity(){return console.warn("`ElementInternals.checkValidity()` was called on the server.This method always returns true."),!0}reportValidity(){return!0}setFormValue(){}setValidity(){}},R=function(t,e,r,i,s){if(i==="m")throw new TypeError("Private method is not writable");if(i==="a"&&!s)throw new TypeError("Private accessor was defined without a setter");if(typeof e=="function"?t!==e||!s:!e.has(t))throw new TypeError("Cannot write private member to an object whose class did not declare it");return i==="a"?s.call(t,r):s?s.value=r:e.set(t,r),r},b=function(t,e,r,i){if(r==="a"&&!i)throw new TypeError("Private accessor was defined without a getter");if(typeof e=="function"?t!==e||!i:!e.has(t))throw new TypeError("Cannot read private member from an object whose class did not declare it");return r==="m"?i:r==="a"?i.call(t):i?i.value:e.get(t)},X,wt,Et,st,Ut,ot,At,V,nt,j,xt,ee,re=t=>typeof t=="boolean"?t:t?.capture??!1,Pt=0,Ht=1,It=2,jt=3,Re=class{constructor(){this.__eventListeners=new Map,this.__captureEventListeners=new Map}addEventListener(e,r,i){if(r==null)return;let s=re(i)?this.__captureEventListeners:this.__eventListeners,a=s.get(e);if(a===void 0)a=new Map,s.set(e,a);else if(a.has(r))return;let o=typeof i=="object"&&i?i:{};o.signal?.addEventListener("abort",()=>this.removeEventListener(e,r,i)),a.set(r,o??{})}removeEventListener(e,r,i){if(r==null)return;let s=re(i)?this.__captureEventListeners:this.__eventListeners,a=s.get(e);a!==void 0&&(a.delete(r),a.size||s.delete(e))}dispatchEvent(e){let r=[this],i=this.__eventTargetParent;if(e.composed)for(;i;)r.push(i),i=i.__eventTargetParent;else for(;i&&i!==this.__host;)r.push(i),i=i.__eventTargetParent;let s=!1,a=!1,o=Pt,l=null,n=null,c=null,d=e.stopPropagation,u=e.stopImmediatePropagation;Object.defineProperties(e,{target:{get(){return l??n},...g},srcElement:{get(){return e.target},...g},currentTarget:{get(){return c},...g},eventPhase:{get(){return o},...g},composedPath:{value:()=>r,...g},stopPropagation:{value:()=>{s=!0,d.call(e)},...g},stopImmediatePropagation:{value:()=>{a=!0,u.call(e)},...g}});let f=(y,U,it)=>{typeof y=="function"?y(e):typeof y?.handleEvent=="function"&&y.handleEvent(e),U.once&&it.delete(y)},v=()=>(c=null,o=Pt,!e.defaultPrevented),O=r.slice().reverse();l=!this.__host||!e.composed?this:null;let $t=y=>{for(n=this;n.__host&&y.includes(n.__host);)n=n.__host};for(let y of O){!l&&(!n||n===y.__host)&&$t(O.slice(O.indexOf(y))),c=y,o=y===e.target?It:Ht;let U=y.__captureEventListeners.get(e.type);if(U){for(let[it,Lt]of U)if(f(it,Lt,U),a)return v()}if(s)return v()}let rt=e.bubbles?r:[this];n=null;for(let y of rt){!l&&(!n||y===n.__host)&&$t(rt.slice(0,rt.indexOf(y)+1)),c=y,o=y===e.target?It:jt;let U=y.__eventListeners.get(e.type);if(U){for(let[it,Lt]of U)if(f(it,Lt,U),a)return v()}if(s)return v()}return v()}},Ne=Re,g={__proto__:null};g.enumerable=!0,Object.freeze(g);var Bt=(j=class{constructor(e,r={}){if(X.set(this,!1),wt.set(this,!1),Et.set(this,!1),st.set(this,!1),Ut.set(this,Date.now()),ot.set(this,!1),At.set(this,void 0),V.set(this,void 0),nt.set(this,void 0),this.NONE=Pt,this.CAPTURING_PHASE=Ht,this.AT_TARGET=It,this.BUBBLING_PHASE=jt,arguments.length===0)throw new Error("The type argument must be specified");if(typeof r!="object"||!r)throw new Error('The "options" argument must be an object');let{bubbles:i,cancelable:s,composed:a}=r;R(this,X,!!s,"f"),R(this,wt,!!i,"f"),R(this,Et,!!a,"f"),R(this,At,`${e}`,"f"),R(this,V,null,"f"),R(this,nt,!1,"f")}initEvent(e,r,i){throw new Error("Method not implemented.")}stopImmediatePropagation(){this.stopPropagation()}preventDefault(){R(this,st,!0,"f")}get target(){return b(this,V,"f")}get currentTarget(){return b(this,V,"f")}get srcElement(){return b(this,V,"f")}get type(){return b(this,At,"f")}get cancelable(){return b(this,X,"f")}get defaultPrevented(){return b(this,X,"f")&&b(this,st,"f")}get timeStamp(){return b(this,Ut,"f")}composedPath(){return b(this,nt,"f")?[b(this,V,"f")]:[]}get returnValue(){return!b(this,X,"f")||!b(this,st,"f")}get bubbles(){return b(this,wt,"f")}get composed(){return b(this,Et,"f")}get eventPhase(){return b(this,nt,"f")?j.AT_TARGET:j.NONE}get cancelBubble(){return b(this,ot,"f")}set cancelBubble(e){e&&R(this,ot,!0,"f")}stopPropagation(){R(this,ot,!0,"f")}get isTrusted(){return!1}},X=new WeakMap,wt=new WeakMap,Et=new WeakMap,st=new WeakMap,Ut=new WeakMap,ot=new WeakMap,At=new WeakMap,V=new WeakMap,nt=new WeakMap,j.NONE=Pt,j.CAPTURING_PHASE=Ht,j.AT_TARGET=It,j.BUBBLING_PHASE=jt,j);Object.defineProperties(Bt.prototype,{initEvent:g,stopImmediatePropagation:g,preventDefault:g,target:g,currentTarget:g,srcElement:g,type:g,cancelable:g,defaultPrevented:g,timeStamp:g,composedPath:g,returnValue:g,bubbles:g,composed:g,eventPhase:g,cancelBubble:g,stopPropagation:g,isTrusted:g});var ie=(ee=class extends Bt{constructor(e,r={}){super(e,r),xt.set(this,void 0),R(this,xt,r?.detail??null,"f")}initCustomEvent(e,r,i,s){throw new Error("Method not implemented.")}get detail(){return b(this,xt,"f")}},xt=new WeakMap,ee);Object.defineProperties(ie.prototype,{detail:g});var Le=Bt,Ue=ie;globalThis.Event??=Le,globalThis.CustomEvent??=Ue;var se=new WeakMap,at=t=>{let e=se.get(t);return e===void 0&&se.set(t,e=new Map),e},He=class extends Ne{constructor(){super(...arguments),this.__shadowRootMode=null,this.__shadowRoot=null,this.__internals=null}get attributes(){return Array.from(at(this)).map(([e,r])=>({name:e,value:r}))}get shadowRoot(){return this.__shadowRootMode==="closed"?null:this.__shadowRoot}get localName(){return this.constructor.__localName}get tagName(){return this.localName?.toUpperCase()}setAttribute(e,r){at(this).set(e,String(r))}removeAttribute(e){at(this).delete(e)}toggleAttribute(e,r){if(this.hasAttribute(e)){if(r===void 0||!r)return this.removeAttribute(e),!1}else return r===void 0||r?(this.setAttribute(e,""),!0):!1;return!0}hasAttribute(e){return at(this).has(e)}attachShadow(e){let r={host:this};return this.__shadowRootMode=e.mode,e&&e.mode==="open"&&(this.__shadowRoot=r),r}attachInternals(){if(this.__internals!==null)throw new Error("Failed to execute 'attachInternals' on 'HTMLElement': ElementInternals for the specified element was already attached.");let e=new Me(this);return this.__internals=e,e}getAttribute(e){return at(this).get(e)??null}},je=class extends He{},oe=je;globalThis.litServerRoot??=Object.defineProperty(new oe,"localName",{get(){return"lit-server-root"}});var Be=class{constructor(){this.__definitions=new Map}define(e,r){if(this.__definitions.has(e))throw new Error(`Failed to execute 'define' on 'CustomElementRegistry': the name "${e}" has already been used with this registry`);r.__localName=e,this.__definitions.set(e,{ctor:r,observedAttributes:r.observedAttributes??[]})}get(e){return this.__definitions.get(e)?.ctor}},ze=Be,We=new ze,lt=globalThis,zt=lt.ShadowRoot&&(lt.ShadyCSS===void 0||lt.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Wt=Symbol(),ne=new WeakMap,ae=class{constructor(t,e,r){if(this._$cssResult$=!0,r!==Wt)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(zt&&t===void 0){let r=e!==void 0&&e.length===1;r&&(t=ne.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),r&&ne.set(e,t))}return t}toString(){return this.cssText}},Ve=t=>new ae(typeof t=="string"?t:t+"",void 0,Wt),S=(t,...e)=>{let r=t.length===1?t[0]:e.reduce(((i,s,a)=>i+(o=>{if(o._$cssResult$===!0)return o.cssText;if(typeof o=="number")return o;throw Error("Value passed to 'css' function must be a 'css' function result: "+o+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+t[a+1]),t[0]);return new ae(r,t,Wt)},Ge=(t,e)=>{if(zt)t.adoptedStyleSheets=e.map((r=>r instanceof CSSStyleSheet?r:r.styleSheet));else for(let r of e){let i=document.createElement("style"),s=lt.litNonce;s!==void 0&&i.setAttribute("nonce",s),i.textContent=r.cssText,t.appendChild(i)}},le=zt||lt.CSSStyleSheet===void 0?t=>t:t=>t instanceof CSSStyleSheet?(e=>{let r="";for(let i of e.cssRules)r+=i.cssText;return Ve(r)})(t):t,{is:Fe,defineProperty:qe,getOwnPropertyDescriptor:Ke,getOwnPropertyNames:Xe,getOwnPropertySymbols:Ze,getPrototypeOf:Je}=Object,ht=globalThis;ht.customElements??=We;var he=ht.trustedTypes,Ye=he?he.emptyScript:"",Qe=ht.reactiveElementPolyfillSupport,ct=(t,e)=>t,St={toAttribute(t,e){switch(e){case Boolean:t=t?Ye:null;break;case Object:case Array:t=t==null?t:JSON.stringify(t)}return t},fromAttribute(t,e){let r=t;switch(e){case Boolean:r=t!==null;break;case Number:r=t===null?null:Number(t);break;case Object:case Array:try{r=JSON.parse(t)}catch{r=null}}return r}},Ct=(t,e)=>!Fe(t,e),ce={attribute:!0,type:String,converter:St,reflect:!1,useDefault:!1,hasChanged:Ct};Symbol.metadata??=Symbol("metadata"),ht.litPropertyMetadata??=new WeakMap;var Z=class extends(globalThis.HTMLElement??oe){static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=ce){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let r=Symbol(),i=this.getPropertyDescriptor(t,r,e);i!==void 0&&qe(this.prototype,t,i)}}static getPropertyDescriptor(t,e,r){let{get:i,set:s}=Ke(this.prototype,t)??{get(){return this[e]},set(a){this[e]=a}};return{get:i,set(a){let o=i?.call(this);s?.call(this,a),this.requestUpdate(t,o,r)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??ce}static _$Ei(){if(this.hasOwnProperty(ct("elementProperties")))return;let t=Je(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(ct("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(ct("properties"))){let e=this.properties,r=[...Xe(e),...Ze(e)];for(let i of r)this.createProperty(i,e[i])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[r,i]of e)this.elementProperties.set(r,i)}this._$Eh=new Map;for(let[e,r]of this.elementProperties){let i=this._$Eu(e,r);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let r=new Set(t.flat(1/0).reverse());for(let i of r)e.unshift(le(i))}else t!==void 0&&e.push(le(t));return e}static _$Eu(t,e){let r=e.attribute;return r===!1?void 0:typeof r=="string"?r:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise((t=>this.enableUpdating=t)),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach((t=>t(this)))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let r of e.keys())this.hasOwnProperty(r)&&(t.set(r,this[r]),delete this[r]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ge(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach((t=>t.hostConnected?.()))}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach((t=>t.hostDisconnected?.()))}attributeChangedCallback(t,e,r){this._$AK(t,r)}_$ET(t,e){let r=this.constructor.elementProperties.get(t),i=this.constructor._$Eu(t,r);if(i!==void 0&&r.reflect===!0){let s=(r.converter?.toAttribute!==void 0?r.converter:St).toAttribute(e,r.type);this._$Em=t,s==null?this.removeAttribute(i):this.setAttribute(i,s),this._$Em=null}}_$AK(t,e){let r=this.constructor,i=r._$Eh.get(t);if(i!==void 0&&this._$Em!==i){let s=r.getPropertyOptions(i),a=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:St;this._$Em=i,this[i]=a.fromAttribute(e,s.type)??this._$Ej?.get(i)??null,this._$Em=null}}requestUpdate(t,e,r){if(t!==void 0){let i=this.constructor,s=this[t];if(r??=i.getPropertyOptions(t),!((r.hasChanged??Ct)(s,e)||r.useDefault&&r.reflect&&s===this._$Ej?.get(t)&&!this.hasAttribute(i._$Eu(t,r))))return;this.C(t,e,r)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:r,reflect:i,wrapped:s},a){r&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,a??e??this[t]),s!==!0||a!==void 0)||(this._$AL.has(t)||(this.hasUpdated||r||(e=void 0),this._$AL.set(t,e)),i===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,s]of this._$Ep)this[i]=s;this._$Ep=void 0}let r=this.constructor.elementProperties;if(r.size>0)for(let[i,s]of r){let{wrapped:a}=s,o=this[i];a!==!0||this._$AL.has(i)||o===void 0||this.C(i,void 0,s,o)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach((r=>r.hostUpdate?.())),this.update(e)):this._$EM()}catch(r){throw t=!1,this._$EM(),r}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach((e=>e.hostUpdated?.())),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach((e=>this._$ET(e,this[e]))),this._$EM()}updated(t){}firstUpdated(t){}};Z.elementStyles=[],Z.shadowRootOptions={mode:"open"},Z[ct("elementProperties")]=new Map,Z[ct("finalized")]=new Map,Qe?.({ReactiveElement:Z}),(ht.reactiveElementVersions??=[]).push("2.1.0");var tr={attribute:!0,type:String,converter:St,reflect:!1,hasChanged:Ct},er=(t=tr,e,r)=>{let{kind:i,metadata:s}=r,a=globalThis.litPropertyMetadata.get(s);if(a===void 0&&globalThis.litPropertyMetadata.set(s,a=new Map),i==="setter"&&((t=Object.create(t)).wrapped=!0),a.set(r.name,t),i==="accessor"){let{name:o}=r;return{set(l){let n=e.get.call(this);e.set.call(this,l),this.requestUpdate(o,n,t)},init(l){return l!==void 0&&this.C(o,void 0,t,l),l}}}if(i==="setter"){let{name:o}=r;return function(l){let n=this[o];e.call(this,l),this.requestUpdate(o,n,t)}}throw Error("Unsupported decorator location: "+i)};function p(t){return(e,r)=>typeof r=="object"?er(t,e,r):((i,s,a)=>{let o=s.hasOwnProperty(a);return s.constructor.createProperty(a,i),o?Object.getOwnPropertyDescriptor(s,a):void 0})(t,e,r)}var Vt=[];function Rt(t){let e=I(t);return function(r,i){return Vt.push(r),e(r,i)}}var kt=globalThis,Tt=kt.trustedTypes,de=Tt?Tt.createPolicy("lit-html",{createHTML:t=>t}):void 0,pe="$lit$",B=`lit$${Math.random().toFixed(9).slice(2)}$`,ue="?"+B,rr=`<${ue}>`,G=kt.document===void 0?{createTreeWalker:()=>({})}:document,dt=()=>G.createComment(""),pt=t=>t===null||typeof t!="object"&&typeof t!="function",Gt=Array.isArray,ir=t=>Gt(t)||typeof t?.[Symbol.iterator]=="function",Ft=`[ 	
\f\r]`,ut=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,me=/-->/g,fe=/>/g,F=RegExp(`>|${Ft}(?:([^\\s"'>=/]+)(${Ft}*=${Ft}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),ge=/'/g,_e=/"/g,ve=/^(?:script|style|textarea|title)$/i,qt=t=>(e,...r)=>({_$litType$:t,strings:e,values:r}),m=qt(1),Dt=qt(2),Cr=qt(3),J=Symbol.for("lit-noChange"),_=Symbol.for("lit-nothing"),ye=new WeakMap,q=G.createTreeWalker(G,129);function be(t,e){if(!Gt(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return de!==void 0?de.createHTML(e):e}var sr=(t,e)=>{let r=t.length-1,i=[],s,a=e===2?"<svg>":e===3?"<math>":"",o=ut;for(let l=0;l<r;l++){let n=t[l],c,d,u=-1,f=0;for(;f<n.length&&(o.lastIndex=f,d=o.exec(n),d!==null);)f=o.lastIndex,o===ut?d[1]==="!--"?o=me:d[1]!==void 0?o=fe:d[2]!==void 0?(ve.test(d[2])&&(s=RegExp("</"+d[2],"g")),o=F):d[3]!==void 0&&(o=F):o===F?d[0]===">"?(o=s??ut,u=-1):d[1]===void 0?u=-2:(u=o.lastIndex-d[2].length,c=d[1],o=d[3]===void 0?F:d[3]==='"'?_e:ge):o===_e||o===ge?o=F:o===me||o===fe?o=ut:(o=F,s=void 0);let v=o===F&&t[l+1].startsWith("/>")?" ":"";a+=o===ut?n+rr:u>=0?(i.push(c),n.slice(0,u)+pe+n.slice(u)+B+v):n+B+(u===-2?l:v)}return[be(t,a+(t[r]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),i]},Kt=class Ee{constructor({strings:e,_$litType$:r},i){let s;this.parts=[];let a=0,o=0,l=e.length-1,n=this.parts,[c,d]=sr(e,r);if(this.el=Ee.createElement(c,i),q.currentNode=this.el.content,r===2||r===3){let u=this.el.content.firstChild;u.replaceWith(...u.childNodes)}for(;(s=q.nextNode())!==null&&n.length<l;){if(s.nodeType===1){if(s.hasAttributes())for(let u of s.getAttributeNames())if(u.endsWith(pe)){let f=d[o++],v=s.getAttribute(u).split(B),O=/([.?@])?(.*)/.exec(f);n.push({type:1,index:a,name:O[2],strings:v,ctor:O[1]==="."?nr:O[1]==="?"?ar:O[1]==="@"?lr:Ot}),s.removeAttribute(u)}else u.startsWith(B)&&(n.push({type:6,index:a}),s.removeAttribute(u));if(ve.test(s.tagName)){let u=s.textContent.split(B),f=u.length-1;if(f>0){s.textContent=Tt?Tt.emptyScript:"";for(let v=0;v<f;v++)s.append(u[v],dt()),q.nextNode(),n.push({type:2,index:++a});s.append(u[f],dt())}}}else if(s.nodeType===8)if(s.data===ue)n.push({type:2,index:a});else{let u=-1;for(;(u=s.data.indexOf(B,u+1))!==-1;)n.push({type:7,index:a}),u+=B.length-1}a++}}static createElement(e,r){let i=G.createElement("template");return i.innerHTML=e,i}};function Y(t,e,r=t,i){if(e===J)return e;let s=i!==void 0?r._$Co?.[i]:r._$Cl,a=pt(e)?void 0:e._$litDirective$;return s?.constructor!==a&&(s?._$AO?.(!1),a===void 0?s=void 0:(s=new a(t),s._$AT(t,r,i)),i!==void 0?(r._$Co??=[])[i]=s:r._$Cl=s),s!==void 0&&(e=Y(t,s._$AS(t,e.values),s,i)),e}var or=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:r}=this._$AD,i=(t?.creationScope??G).importNode(e,!0);q.currentNode=i;let s=q.nextNode(),a=0,o=0,l=r[0];for(;l!==void 0;){if(a===l.index){let n;l.type===2?n=new Xt(s,s.nextSibling,this,t):l.type===1?n=new l.ctor(s,l.name,l.strings,this,t):l.type===6&&(n=new hr(s,this,t)),this._$AV.push(n),l=r[++o]}a!==l?.index&&(s=q.nextNode(),a++)}return q.currentNode=G,i}p(t){let e=0;for(let r of this._$AV)r!==void 0&&(r.strings!==void 0?(r._$AI(t,r,e),e+=r.strings.length-2):r._$AI(t[e])),e++}},Xt=class Ae{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,r,i,s){this.type=2,this._$AH=_,this._$AN=void 0,this._$AA=e,this._$AB=r,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,r=this._$AM;return r!==void 0&&e?.nodeType===11&&(e=r.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,r=this){e=Y(this,e,r),pt(e)?e===_||e==null||e===""?(this._$AH!==_&&this._$AR(),this._$AH=_):e!==this._$AH&&e!==J&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):ir(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==_&&pt(this._$AH)?this._$AA.nextSibling.data=e:this.T(G.createTextNode(e)),this._$AH=e}$(e){let{values:r,_$litType$:i}=e,s=typeof i=="number"?this._$AC(e):(i.el===void 0&&(i.el=Kt.createElement(be(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(r);else{let a=new or(s,this),o=a.u(this.options);a.p(r),this.T(o),this._$AH=a}}_$AC(e){let r=ye.get(e.strings);return r===void 0&&ye.set(e.strings,r=new Kt(e)),r}k(e){Gt(this._$AH)||(this._$AH=[],this._$AR());let r=this._$AH,i,s=0;for(let a of e)s===r.length?r.push(i=new Ae(this.O(dt()),this.O(dt()),this,this.options)):i=r[s],i._$AI(a),s++;s<r.length&&(this._$AR(i&&i._$AB.nextSibling,s),r.length=s)}_$AR(e=this._$AA.nextSibling,r){for(this._$AP?.(!1,!0,r);e&&e!==this._$AB;){let i=e.nextSibling;e.remove(),e=i}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},Ot=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,r,i,s){this.type=1,this._$AH=_,this._$AN=void 0,this.element=t,this.name=e,this._$AM=i,this.options=s,r.length>2||r[0]!==""||r[1]!==""?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=_}_$AI(t,e=this,r,i){let s=this.strings,a=!1;if(s===void 0)t=Y(this,t,e,0),a=!pt(t)||t!==this._$AH&&t!==J,a&&(this._$AH=t);else{let o=t,l,n;for(t=s[0],l=0;l<s.length-1;l++)n=Y(this,o[r+l],e,l),n===J&&(n=this._$AH[l]),a||=!pt(n)||n!==this._$AH[l],n===_?t=_:t!==_&&(t+=(n??"")+s[l+1]),this._$AH[l]=n}a&&!i&&this.j(t)}j(t){t===_?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},nr=class extends Ot{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===_?void 0:t}},ar=class extends Ot{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==_)}},lr=class extends Ot{constructor(t,e,r,i,s){super(t,e,r,i,s),this.type=5}_$AI(t,e=this){if((t=Y(this,t,e,0)??_)===J)return;let r=this._$AH,i=t===_&&r!==_||t.capture!==r.capture||t.once!==r.once||t.passive!==r.passive,s=t!==_&&(r===_||i);i&&this.element.removeEventListener(this.name,this,r),s&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},hr=class{constructor(t,e,r){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(t){Y(this,t)}},cr=kt.litHtmlPolyfillSupport;cr?.(Kt,Xt),(kt.litHtmlVersions??=[]).push("3.3.0");var dr=(t,e,r)=>{let i=r?.renderBefore??e,s=i._$litPart$;if(s===void 0){let a=r?.renderBefore??null;i._$litPart$=s=new Xt(e.insertBefore(dt(),a),a,void 0,r??{})}return s._$AI(t),s},Zt=globalThis,M=class extends Z{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=dr(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return J}};M._$litElement$=!0,M.finalized=!0,Zt.litElementHydrateSupport?.({LitElement:M});var pr=Zt.litElementPolyfillSupport;pr?.({LitElement:M}),(Zt.litElementVersions??=[]).push("4.2.0");var H=class extends M{render(){if(this.annotation&&this.item&&this.page&&this.canDrawAnnotation(this.annotation)&&this.canDrawItem(this.item))return this.renderAnnotation(this.annotation,this.item,this.page,this.prov)}};h([p({attribute:!1})],H.prototype,"annotation",2),h([p({attribute:!1})],H.prototype,"item",2),h([p({attribute:!1})],H.prototype,"page",2),h([p({attribute:!1})],H.prototype,"prov",2);var ur=["title","document_index","section_header","paragraph","table","picture","formula","checkbox_unselected","checkbox_selected","text","list_item","code","reference","page_header","page_footer","key_value_region","empty_value","field_key","field_value","field_heading","field_hint","marker","handwritten_text"],kr=[...ur,"footnote","caption","form"];function A(...t){return function(e){return w.DocItem(e)&&t.includes(e.label)}}var $={CodeItem:A("code"),FieldHeadingItem:A("field_heading"),FieldItem:A("field_item"),FieldRegionItem:A("field_region"),FieldValueItem:A("field_value"),FormItem:A("form"),FormulaItem:A("formula"),KeyValueItem:A("key_value_region"),ListItem:A("list_item"),PictureItem:A("chart","picture"),SectionHeaderItem:A("section_header"),TableItem:A("document_index","table"),TextItem:A("caption","checkbox_selected","checkbox_unselected","empty_value","field_hint","field_key","footnote","grading_scale","handwritten_text","marker","page_footer","page_header","paragraph","reference","text"),TitleItem:A("title")};function N(...t){return function(e){return t.includes(e.kind)}}var Jt={PictureBarChart:N("bar_chart_data"),PictureClassification:N("classification"),PictureDescription:N("description"),PictureMisc:N("misc"),PictureMolecule:N("molecule_data"),PictureLineChart:N("line_chart_data"),PicturePieChart:N("pie_chart_data"),PictureScatterChart:N("scatter_chart_data"),PictureStackedBarChart:N("stacked_bar_chart_data"),PictureTabularChart:N("tabular_chart_data")},w={DocItem(t){return w.NodeItem(t)&&!w.GroupItem(t)},Document(t){return"schema_name"in t&&t.schema_name==="DoclingDocument"},GroupItem(t){return w.NodeItem(t)&&(t.self_ref.startsWith("#/groups/")||t.self_ref==="#/body"||t.self_ref==="#/furniture")},ListGroup(t){return w.GroupItem(t)&&"label"in t&&t.label==="list"},OrderedList(t){return w.GroupItem(t)&&"label"in t&&t.label==="ordered_list"},InlineGroup(t){return w.GroupItem(t)&&"label"in t&&t.label==="inline"},NodeItem(t){return"self_ref"in t},...Jt,...$};function*mr(t,e={}){t&&(yield*r(e.root??t.body));function*r(i,s=0){(!w.GroupItem(i)||e.withGroups)&&(w.DocItem(i)?(e.pageNo===void 0||i.prov?.some(l=>l.page_no===e.pageNo))&&(yield[i,s]):yield[i,s]);let a=w.PictureItem(i),o=new Set(a?(i.captions??[]).map(l=>l.$ref):[]);for(let l of i.children??[]){if(a&&!e.traversePictures&&!o.has(l.$ref))continue;let n=fr(t,l);w.NodeItem(n)&&(yield*r(n,s+1))}}}function fr(t,e){return e.$ref.split("/").slice(1).reduce((i,s)=>i[s],t)}var Q=class extends H{constructor(){super(...arguments),this.precision=2}renderAnnotation(t,e,r,i){let s=t.predicted_classes??[],a=Math.pow(10,-1*this.precision),o=s.filter(c=>a<c.confidence),l=s.filter(c=>c.confidence<a),n=c=>c.toLocaleString(void 0,{maximumFractionDigits:this.precision});return m`<table>
      <thead>
        <tr>
          <th>Class</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        ${o.map(({class_name:c,confidence:d})=>m`<tr>
              <td>${c}</td>
              <td>${n(d)}</td>
            </tr>`)}
        ${l.length===0?_:m`<tr
                class="more"
                title=${l.map(c=>`${c.class_name}			${c.confidence}`).join(`
`)}
              >
                <td>${l.length} more</td>
                <td>< ${n(a)}</td>
              </tr>`}
      </tbody>
    </table>`}canDrawAnnotation(t){return Jt.PictureClassification(t)}canDrawItem(t){return $.PictureItem(t)}};Q.styles=S`
    table {
      margin: 0.5rem;
      font-size: inherit;
      line-height: 1.25;
    }

    td,
    th {
      padding: 0 1rem 0 0;
    }

    th {
      font-weight: bold;
      text-align: left;
    }

    tr.more td {
      padding-top: 0.25rem;
      color: gray;
    }
  `,h([p()],Q.prototype,"precision",2),Q=h([Rt("docling-picture-classification")],Q);var mt=class extends H{renderAnnotation(t,e,r,i){return m`<p><span>Description</span>${t.text}</p>`}canDrawAnnotation(t){return Jt.PictureDescription(t)}canDrawItem(t){return $.PictureItem(t)}};mt.styles=S`
    p {
      margin: 0.5rem;
      font-size: inherit;
      line-height: 1.25;
      white-space: pre-line;
    }

    span {
      padding-right: 0.5rem;
      font-weight: bold;
    }
  `,mt=h([Rt("docling-picture-description")],mt);var Yt=[];function tt(t){let e=I(t);return function(r,i){return Yt.push(r),e(r,i)}}var C=class extends M{render(){if(this.item&&this.page&&this.canDrawItem(this.item)){let t=this.item.level??0;return this.setAttribute("data-level",String(t)),this.style.setProperty("--docling-level",String(t)),this.setAttribute("data-layer",this.item.content_layer??""),this.renderItem(this.item,this.page,this.prov)}}static{this.styles=S`
    :host([data-layer='furniture']) {
      opacity: 0.33;
    }
  `}};h([p({attribute:!1})],C.prototype,"item",2),h([p({attribute:!1})],C.prototype,"page",2),h([p({attribute:!1})],C.prototype,"prov",2);var ft=class extends C{renderItem(t,e,r){return m`
      <div class="code-block">
        ${t.code_language?m`<span class="lang">${t.code_language}</span>`:_}
        <pre><code>${t.text}</code></pre>
      </div>
    `}canDrawItem(t){return $.CodeItem(t)}};ft.styles=S`
    .code-block {
      position: relative;
      margin: 0;
      background: #f4f4f4;
      border-left: 3px solid #bbb;
      border-radius: 2px;
      overflow: auto;
    }

    .lang {
      position: absolute;
      top: 0.15rem;
      right: 0.4rem;
      font-size: 0.65rem;
      color: #888;
      font-family: monospace;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    pre {
      margin: 0;
      padding: 0.4rem 0.5rem;
      font-size: 0.75rem;
      line-height: 1.4;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: monospace;
    }

    code {
      font-family: inherit;
    }
  `,ft=h([tt("docling-item-code")],ft);var gt=class extends C{renderItem(t,e,r){let i=t.graph?.cells??[],s=t.graph?.links??[],a=new Map(i.map(l=>[l.cell_id,l])),o=[];for(let l of s)if(l.label==="to_value"){let n=a.get(l.source_cell_id),c=a.get(l.target_cell_id);n&&c&&o.push({key:n.text,value:c.text})}if(o.length===0){let l=i.filter(d=>d.label==="key"),n=i.filter(d=>d.label==="value"),c=Math.max(l.length,n.length);for(let d=0;d<c;d++)o.push({key:l[d]?.text??"",value:n[d]?.text??""})}return o.length===0?m`${_}`:m`
      <table class="kv">
        <tbody>
          ${o.map(({key:l,value:n})=>m`
              <tr>
                <td class="key">${l}</td>
                <td class="value">${n}</td>
              </tr>
            `)}
        </tbody>
      </table>
    `}canDrawItem(t){return $.KeyValueItem(t)}};gt.styles=S`
    .kv {
      border-collapse: collapse;
      font-size: 75%;
      line-height: 1.25;
      width: 100%;
    }

    td {
      padding: 0.1rem 0.3rem;
      border: 1px solid rgb(220, 220, 220);
      vertical-align: top;
      word-break: break-word;
    }

    td.key {
      font-weight: bold;
      white-space: nowrap;
      color: #444;
      width: 40%;
    }

    td.value {
      color: #111;
    }
  `,gt=h([tt("docling-item-key-value")],gt);var et=class extends C{renderItem(t,e){let{image:r}=e,i=t.prov?.find(s=>s.page_no===this.page?.page_no);if(r&&i){let{width:s=1,height:a=1}=this.page.size,{l:o,r:l,t:n,b:c}=z(i.bbox,e),d=(r.size.width??1)/s,u=(l-o)*d,f=(c-n)*d;return m`
        <svg
          data-width=${u}
          data-height=${f}
          style="--docling-width: ${u}px; --docling-height: ${f}px;"
          viewBox="${o} ${n} ${l-o} ${c-n}"
        >
          <image href=${r.uri} width=${s} height=${a} />
        </svg>
      `}else return m`<span>Invalid provenance.</span>`}canDrawItem(t){return w.DocItem(t)}};et.styles=S`
    svg {
      width: calc(
        var(--docling-width, 100%) * var(--docling-provenance-scale, 1)
      );
      max-width: 100%;
    }
  `,et=h([I("docling-item-provenance")],et);var _t=class extends C{renderItem(t){let e=new Set;return m`
      <div class="container">
        <table>
          <tbody>
            ${t.data.grid.map(i=>m`<tr>
                  ${i.map(s=>{if(!r(s))return m`<td
                        class=${s.column_header||s.row_header?"header":""}
                        colspan=${s.col_span??1}
                        rowspan=${s.row_span??1}
                      >
                        ${s.text}
                      </td>`})}
                </tr>`)}
          </tbody>
        </table>
      </div>
    `;function r(i){let s=e.has([i.start_col_offset_idx,i.start_row_offset_idx].join());if(!s)for(let a=i.start_col_offset_idx;a<i.end_col_offset_idx;a++)for(let o=i.start_row_offset_idx;o<i.end_row_offset_idx;o++)e.add([a,o].join());return s}}canDrawItem(t){return $.TableItem(t)}};_t.styles=S`
    .container {
      position: relative;
      min-width: 0;
      max-width: 100%;
      min-height: 0;
      overflow: auto;
    }

    table {
      border-collapse: collapse;
      font-size: 75%;
      line-height: 1.25;
    }

    td {
      padding: 0.125rem 0.25rem;
      background-color: var(--cds-layer);
      border: 1px solid rgb(220, 220, 220);

      color: black;
      text-decoration: none;
      word-break: normal;
      text-align: left;
    }

    td.header {
      font-weight: bold;
    }

    td:hover {
      filter: brightness(95%);
    }

    td:target {
      outline: 3px solid blue;
    }
  `,_t=h([tt("docling-item-table")],_t);var Nt=class extends C{constructor(){super(...arguments),this.renderItem=Function("item","page",`"use strict"; return this.html\`${this.innerHTML}\`;`).bind({html:m})}canDrawItem(t){return w.DocItem(t)}};Nt=h([I("docling-item-template")],Nt);var vt=class extends C{renderItem(t,e,r){let i=t.formatting,s=[i?.bold?"font-weight:bold":"",i?.italic?"font-style:italic":"",i?.underline?"text-decoration:underline":"",i?.strikethrough?"text-decoration:line-through":""].filter(Boolean).join(";");if(r){let{l:a,r:o,t:l,b:n}=z(r.bbox,e),c=Math.sqrt((o-a)*(n-l)/t.text.length),d=Math.min(Math.floor(1.25*c),(n-l)/1.25),[u,f]=r.charspan??[0,t.text.length],v=t.text.substring(u,f);return m`<p
        class=${this.textClass(t)}
        style="font-size:${d}px;line-height:${1.25*d}px;${s}"
      >
        ${this.listPrefix(t)}${v}
      </p>`}else return m`<p class=${this.textClass(t)} style=${s||_}>
        ${this.listPrefix(t)}${t.text}
      </p>`}textClass(t){if($.TitleItem(t))return"title";if($.SectionHeaderItem(t)){let e=t.level??1;return`header header-${Math.min(e,6)}`}return $.ListItem(t)?"list-item":""}listPrefix(t){if(!$.ListItem(t))return _;let e=t;return e.marker?m`<span class="marker">${e.marker}</span>`:e.enumerated?m`<span class="marker bullet">•</span>`:m`<span class="marker bullet">–</span>`}canDrawItem(t){return $.TextItem(t)||$.TitleItem(t)||$.SectionHeaderItem(t)||$.ListItem(t)||$.FormulaItem(t)}};vt.styles=S`
    p {
      margin: 0;
      overflow-wrap: anywhere;
      font-size: 1rem;
      line-height: 1.25rem;
    }

    .title {
      font-size: 1.1rem;
      font-weight: bold;
    }

    /* header-1 is largest (document section), header-6 is smallest. */
    .header {
      font-weight: bold;
    }
    .header-1 {
      font-size: 1rem;
    }
    .header-2 {
      font-size: 0.95rem;
    }
    .header-3 {
      font-size: 0.9rem;
    }
    .header-4,
    .header-5,
    .header-6 {
      font-size: 0.85rem;
    }

    .list-item {
      display: flex;
      gap: 0.25rem;
    }

    .marker {
      flex-shrink: 0;
      min-width: 1rem;
    }
  `,vt=h([tt("docling-item-text")],vt);var K=class extends C{get itemChildren(){return Array.from(this.childNodes??[]).filter(t=>t instanceof C)}get annotationChildren(){return Array.from(this.childNodes).filter(t=>t instanceof H)}get isCustomized(){return this.itemChildren.length>0||this.annotationChildren.length>0}renderItem(t,e,r){let i=[],s=this.isCustomized;s?this.itemChildren.filter(o=>o.canDrawItem(t)).forEach(o=>i.push(o)):Yt.filter(o=>o.prototype.canDrawItem(t)).forEach(o=>i.push(new o));let a=[];if($.PictureItem(t)){let l=t.meta;if(l?.description?.text){let n={kind:"description",text:l.description.text,provenance:l.description.created_by??""};a.push(n)}l?.classification?.predictions?.length&&a.push({kind:"classification",provenance:"meta",predicted_classes:l.classification.predictions.map(n=>({class_name:n.class_name,confidence:n.confidence??1}))})}for(let o of a){let l=[];s?this.annotationChildren.filter(n=>n.canDrawItem(n)&&n.canDrawAnnotation(o)).forEach(n=>l.push(n.cloneNode(!0))):Vt.filter(n=>n.prototype.canDrawItem(t)&&n.prototype.canDrawAnnotation(o)).forEach(n=>l.push(new n));for(let n of l)n.annotation=o;i.push(...l)}for(let o of i)o.item=t,o.page=e,o.prov=r;return m`${i}`}canDrawItem(t){return w.DocItem(t)&&this.isCustomized?this.itemChildren.some(e=>e.canDrawItem(t))||this.annotationChildren.some(e=>e.canDrawItem(t)&&t.annotations?.some(r=>e.canDrawAnnotation(r))):Yt.some(e=>e.prototype.canDrawItem(t))||Vt.some(e=>e.prototype.canDrawItem(t)&&t.annotations?.some(r=>e.prototype.canDrawAnnotation(r)))}};K=h([I("docling-view")],K);var yt=class extends K{constructor(){super(...arguments),this.type="overlay"}};yt=h([I("docling-overlay")],yt);var bt=class extends K{constructor(){super(...arguments),this.type="tooltip"}};bt=h([I("docling-tooltip")],bt);function z(t,e){let{height:r=1}=e.size;return t.coord_origin==="TOPLEFT"?t:{...t,t:r-t.t,b:r-t.b}}var E=class extends M{constructor(){super(...arguments),this.pagenumbers=!1}render(){if(this.page?.image){let{image:t,size:e,page_no:r}=this.page,{width:i=1,height:s=1}=e,a=this.onClickItem&&this.page?(o,l)=>this.onClickItem?.(o,this.page,l):void 0;return m`
        <div class="page" @onclick=${o=>a?.(o)}>
          <svg
            class="base"
            width=${t.size.width}
            viewBox="0 0 ${i} ${s}"
          >
            ${this.backdrop?Dt`
                <image
                  class="backdrop"
                  href=${t.uri}
                  width=${i}
                  height=${s}
                />

                <clippath id="clip-page-${r}">
                  ${this.items?.map(o=>{let l=o.prov?.find(n=>n.page_no===r);if(l){let{l:n,r:c,t:d,b:u}=z(l.bbox,this.page);return Dt`<rect
                        x=${n}
                        y=${d}
                        width=${c-n}
                        height=${u-d}
                      />`}})}
                </clippath>
              `:_}

            <image
              id="image"
              href=${t.uri}
              clip-path="url(#clip-page-${r})"
              width=${i}
              height=${s}
            />

            ${this.items?.flatMap(o=>(o.prov??[]).filter(l=>l.page_no===r).map(l=>{let{l:n,r:c,t:d,b:u}=z(l.bbox,this.page);return Dt`
                  ${this.layOver(o,l)}

                  <rect
                  part=${"item"+(this.itemPart?" "+this.itemPart(this.page,o):"")}
                  style=${this.itemStyle?.(this.page,o)}
                  x=${n}
                  y=${d}
                  width=${c-n}
                  height=${u-d}
                  vector-effect="non-scaling-stroke"
                  @click=${f=>{f.stopPropagation(),a?.(f,o)}}
                  @mouseenter=${f=>{let v=f.currentTarget.getBoundingClientRect(),O=[v.top*window.innerWidth,(window.innerWidth-v.right)*window.innerHeight,(window.innerHeight-v.bottom)*window.innerWidth,v.left*window.innerHeight],$t=Math.max(...O),rt=O.findIndex(y=>y===$t);this.attachTooltip(o,l,v,rt)}}
                  @mouseleave=${()=>this.removeTooltip()}
                  />
                `}))}
          </svg>

          ${this.renderTrace()}
          ${this.pagenumbers?m`<header
                    part="page-number-top"
                    class="page-number-top"
                    title="Page ${r}"
                  >
                    ${r}
                  </header>

                  <header
                    part="page-number-bottom"
                    class="page-number-bottom"
                    title="Page ${r}"
                  >
                    ${r}
                  </header>`:_}
        </div>
      `}else return m`Invalid page image.`}layOver(t,e){if(this.overlay?.canDrawItem(t)){let r=this.overlay.cloneNode(!0);r.item=t,r.page=this.page,r.prov=e;let{l:i,r:s,t:a,b:o}=z(e.bbox,this.page),l=$.PictureItem(t)?"softOverlay":"hardOverlay";return Dt`<foreignObject part="overlay" class=${l} x=${i} y=${a} width=${s-i} height=${o-a}>${r}</foreignObject>`}}attachTooltip(t,e,r,i){if(this.tooltip?.canDrawItem(t)){let s=this.tooltip.cloneNode(!0);s.id="tooltip",s.setAttribute("part","tooltip"),s.className="tooltip",s.setAttribute("style",`
        ${i===1?`left: ${r.right}px`:i===3?`right: ${window.outerWidth-r.left}px`:`left: calc(${r.left}px - 2rem)`};
        ${i===0?`bottom: ${window.innerHeight-r.top}px`:i===2?`top: ${r.bottom}px`:`top: calc(${r.top}px - 2rem)`};
        max-width: ${2*Math.max(e.bbox.r-e.bbox.l,200)}px;
        `),s.item=t,s.page=this.page,this.renderRoot.appendChild(s)}}removeTooltip(){this.renderRoot.querySelector("#tooltip")?.remove()}renderTrace(){if(this.trace){let t=this.trace.cloneNode(!0);return t.page=this.page,t.items=this.items,t}}};E.styles=S`
    .page {
      position: relative;
      width: fit-content;
      color: black;
    }

    .base {
      max-width: 100%;
    }

    svg:not(.base) {
      position: absolute;
      inset: 0;
    }

    .backdrop {
      opacity: 0.3;
    }

    .page-number-top,
    .page-number-bottom {
      position: absolute;
      left: 0;
      width: fit-content;
      padding: 0 0.25rem;

      font-size: 0.75rem;
      line-height: 1rem;
      color: rgb(120, 120, 120);
      mix-blend-mode: difference;
    }

    .page-number-top {
      top: 0;
    }

    .page-number-bottom {
      bottom: 0;
    }

    rect {
      fill: blue;
      fill-opacity: 0.0001; /* To activate hover. */
      stroke: grey;
      stroke-width: 1px;
      stroke-dasharray: 1;
      cursor: pointer;
    }

    rect:hover {
      fill-opacity: 0.1;
      stroke: blue;
    }

    rect:target {
      stroke: blue;
      stroke-width: 3px;
      stroke-dasharray: none;
    }

    .hardOverlay,
    .softOverlay {
      font-size: 62.5%;
      background-color: white;
    }

    .softOverlay {
      opacity: 0.9;
    }

    .tooltip {
      position: fixed;
      z-index: 100;
      padding: 1rem;
      margin: 1rem;

      background: white;
      border: 1px solid rgb(230, 230, 230);
      box-shadow: 0 0.5rem 1rem 0 rgba(0, 0, 0, 0.2);
    }
  `,h([p({type:Object})],E.prototype,"page",2),h([p({type:Array})],E.prototype,"items",2),h([p({type:Boolean})],E.prototype,"pagenumbers",2),h([p()],E.prototype,"itemPart",2),h([p()],E.prototype,"itemStyle",2),h([p()],E.prototype,"onClickItem",2),h([p({type:Boolean})],E.prototype,"backdrop",2),h([p({type:Object})],E.prototype,"overlay",2),h([p({type:Object})],E.prototype,"tooltip",2),h([p({type:Object})],E.prototype,"trace",2),E=h([I("docling-img-page")],E);var gr=Symbol(),$e=class{get taskComplete(){return this.t||(this.i===1?this.t=new Promise(((t,e)=>{this.o=t,this.h=e})):this.i===3?this.t=Promise.reject(this.l):this.t=Promise.resolve(this.u)),this.t}constructor(t,e,r){this.p=0,this.i=0,(this._=t).addController(this);let i=typeof e=="object"?e:{task:e,args:r};this.v=i.task,this.j=i.args,this.m=i.argsEqual??_r,this.k=i.onComplete,this.A=i.onError,this.autoRun=i.autoRun??!0,"initialValue"in i&&(this.u=i.initialValue,this.i=2,this.O=this.T?.())}hostUpdate(){this.autoRun===!0&&this.S()}hostUpdated(){this.autoRun==="afterUpdate"&&this.S()}T(){if(this.j===void 0)return;let t=this.j();if(!Array.isArray(t))throw Error("The args function must return an array");return t}async S(){let t=this.T(),e=this.O;this.O=t,t===e||t===void 0||e!==void 0&&this.m(e,t)||await this.run(t)}async run(t){let e,r;t??=this.T(),this.O=t,this.i===1?this.q?.abort():(this.t=void 0,this.o=void 0,this.h=void 0),this.i=1,this.autoRun==="afterUpdate"?queueMicrotask((()=>this._.requestUpdate())):this._.requestUpdate();let i=++this.p;this.q=new AbortController;let s=!1;try{e=await this.v(t,{signal:this.q.signal})}catch(a){s=!0,r=a}if(this.p===i){if(e===gr)this.i=0;else{if(s===!1){try{this.k?.(e)}catch{}this.i=2,this.o?.(e)}else{try{this.A?.(r)}catch{}this.i=3,this.h?.(r)}this.u=e,this.l=r}this._.requestUpdate()}}abort(t){this.i===1&&this.q?.abort(t)}get value(){return this.u}get error(){return this.l}get status(){return this.i}render(t){switch(this.i){case 0:return t.initial?.();case 1:return t.pending?.();case 2:return t.complete?.(this.value);case 3:return t.error?.(this.error);default:throw Error("Unexpected status: "+this.i)}}},_r=(t,e)=>t===e||t.length===e.length&&t.every(((r,i)=>!Ct(r,e[i])));function vr(t){return Object.values(t?.pages??{}).sort((e,r)=>e.page_no-r.page_no)}async function we(t,e={}){let r;typeof t=="string"?r=await(await fetch(t)).json():typeof t=="object"&&w.Document(t)&&(r=t);let i=vr(r),s=Array.from(mr(r,{traversePictures:!0})).map(([n,c])=>Object.assign(n,{level:c})),a=s,o=new Set;if(typeof e.items=="string"){let n=new Set(e.items.split(",").map(c=>c.trim()).filter(c=>c.length>0));if(n.size>0){a=[];for(let c of s){let d=c.self_ref.split("/"),u=[];for(let f=2;f<d.length+1;f++)u.push(d.slice(0,f).join("/"));c.prov?.forEach(f=>u.push(`#/pages/${f.page_no}`)),u.some(f=>n.has(f))?a.push(c):c.prov?.forEach(f=>o.add(f.page_no))}}}else if(Array.isArray(e.items)){a=[];let n=new Set(e.items);for(let c of s)n.has(c)?a.push(c):c.prov?.forEach(d=>o.add(d.page_no))}let l={};for(let n of i)l[n.page_no]=[];for(let n of a)for(let c of n.prov??[])l[c.page_no].at(-1)!==n&&l[c.page_no].push(n);return i.map(n=>({page:n,items:l[n.page_no],trimmed:o.has(n.page_no)}))}var W=class extends M{render(){if(this.page&&this.items&&this.items.length>0){let{page_no:t,size:e}=this.page,{width:r=1,height:i=1}=e,s=this.items.map(o=>{let l=o.prov?.find(c=>c.page_no===t)?.bbox,n=z(l??{l:0,t:0,r:0,b:0},this.page);return[(n.l+n.r)/2,(n.t+n.b)/2]}),a=`M${s[0][0]} 0 ${s.slice(0).map(o=>`L${o[0]} ${o[1]}`)} L${s.at(-1)[0]} ${i}`;return m`<svg viewBox="0 0 ${r} ${i}">
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="0"
          refY="5"
          markerWidth="4"
          markerHeight="4"
          orient="auto"
        >
          <path d="M 0 0 L 10 5 L 0 10" />
        </marker>

        <path
          class="halo"
          vector-effect="non-scaling-stroke"
          d=${a}
          marker-start="url(#arrow)"
        />

        <path
          class="trace"
          vector-effect="non-scaling-stroke"
          d=${a}
          marker-start="url(#arrow)"
        />
      </svg>`}}};W.styles=S`
    svg {
      position: absolute;
      inset: 0;
      pointer-events: none;
    }

    .halo {
      fill: none;
      stroke-width: 5px;
      stroke: white;
      stroke-linejoin: round;
    }

    .trace {
      fill: none;
      stroke-width: 3px;
      stroke: rgba(0, 0, 255);
      stroke-linejoin: round;
    }

    marker > path {
      fill: rgba(0, 0, 255);
      stroke: none;
    }
  `,h([p({type:Object})],W.prototype,"page",2),h([p({type:Array})],W.prototype,"items",2),W=h([I("docling-trace")],W);var x=class extends M{constructor(){super(...arguments),this.src="",this.trim="pages",this.fetchTask=new $e(this,{task:async([t,e])=>we(t,{items:e}),args:()=>[this.src,this.items]})}render(){let t=Array.from(this.childNodes);return this.fetchTask.render({pending:()=>m`<p>...</p>`,complete:e=>m`
        ${e.filter(r=>!this.trim||r.items.length>0).map(({page:r,items:i})=>m`<docling-img-page
                part="page"
                .page=${r}
                .items=${i}
                .pagenumbers=${this.pagenumbers!==void 0}
                .itemPart=${this.itemPart}
                .itemStyle=${this.itemStyle}
                .onClickItem=${this.onClickItem}
                .backdrop=${this.backdrop!==void 0}
                .overlay=${t.find(s=>s instanceof yt)}
                .tooltip=${t.find(s=>s instanceof bt)}
                .trace=${t.find(s=>s instanceof W)}
              />`)}
      `})}};x.styles=S`
    :host {
      width: fit-content;

      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;

      color: black;
    }
  `,h([p()],x.prototype,"alt",2),h([p()],x.prototype,"backdrop",2),h([p()],x.prototype,"items",2),h([p({type:Boolean})],x.prototype,"pagenumbers",2),h([p()],x.prototype,"src",2),h([p()],x.prototype,"trim",2),h([p()],x.prototype,"itemPart",2),h([p()],x.prototype,"itemStyle",2),h([p()],x.prototype,"onClickItem",2),x=h([I("docling-img")],x);var k=class extends M{constructor(){super(...arguments),this.columns=[]}render(){return m`
      ${this.pagenumbers?m`
              <tr>
                <td
                  part="page-number-top"
                  class="page-number"
                  title="Page ${this.page?.page_no}"
                  colspan=${this.columns?.length??1}
                >
                  ${this.page?.page_no}
                </td>
              </tr>
            `:_}
      ${this.items?.map(t=>{let e=t.level??0,r=this.itemStyle?.(this.page,t);return m`<tr
          part=${"item"+(this.itemPart?" "+this.itemPart(this.page,t):"")}
          data-level=${e}
          style="--docling-level: ${e}; ${r??""}"
        >
          ${this.columns.map(i=>{let s=i.cloneNode(!0);return s.item=t,s.page=this.page,m`
              <td
                @onclick=${a=>this.onClickItem?.(a,this.page,t)}
              >
                ${s}
              </td>
            `})}
        </tr>`})}
      ${this.pagenumbers?m`<tr>
              <td
                part="page-number-bottom"
                class="page-number"
                title="Page ${this.page?.page_no}"
                colspan=${this.columns?.length??1}
              >
                ${this.page?.page_no}
              </td>
            </tr>`:_}
    `}};k.styles=S`
    :host {
      display: table-row-group;
    }

    tbody {
      border-bottom: 1px solid rgb(220, 220, 220);
    }

    .page-number {
      padding: 0.25rem;

      background-color: white;
      color: rgb(120, 120, 120);
      font-size: 0.75rem;
      line-height: 1rem;
    }

    tr {
      cursor: pointer;
    }

    tr:not(:nth-last-child(2)) {
      border-bottom: 1px dotted rgb(220, 220, 220);
    }

    td {
      padding: 1rem;
      background-color: white;
      vertical-align: top;
    }

    td:first-child {
      border-left: calc(
          max(var(--docling-level, 0) - 1, 0) * var(--docling-depth-width, 4px)
        )
        solid var(--docling-depth-color, rgb(160, 160, 160));
    }

    tr:hover td {
      filter: brightness(95%);
    }
  `,h([p({type:Object})],k.prototype,"page",2),h([p({type:Array})],k.prototype,"items",2),h([p({type:Array})],k.prototype,"columns",2),h([p({type:Boolean})],k.prototype,"pagenumbers",2),h([p()],k.prototype,"itemPart",2),h([p()],k.prototype,"itemStyle",2),h([p()],k.prototype,"onClickItem",2),k=h([I("docling-table-page")],k);var Mt=class extends K{constructor(){super(...arguments),this.type="column"}};Mt=h([I("docling-column")],Mt);var T=class extends M{constructor(){super(...arguments),this.src="",this.fetchTask=new $e(this,{task:async([t,e])=>we(t,{items:e}),args:()=>[this.src,this.items]})}render(){let t=Array.from(this.childNodes).filter(r=>r.nodeName.toLowerCase().startsWith("docling-column")),e=t.length>0?t:[new Mt,new Mt];return t.length===0&&e[1].appendChild(new et),this.fetchTask.render({pending:()=>m`<p>...</p>`,complete:r=>m`
        <table part="pages">
          ${r.filter(i=>i.items.length>0).map(({page:i,items:s})=>m`<docling-table-page
                  .page=${i}
                  .items=${s}
                  .columns=${e}
                  .pagenumbers=${this.pagenumbers!==void 0}
                  .itemPart=${this.itemPart}
                  .itemStyle=${this.itemStyle}
                  .onClickItem=${this.onClickItem}
                />`)}
        </table>
      `})}};T.styles=S`
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      background-color: white;
    }
  `,h([p()],T.prototype,"alt",2),h([p()],T.prototype,"items",2),h([p({type:Boolean})],T.prototype,"pagenumbers",2),h([p()],T.prototype,"src",2),h([p()],T.prototype,"itemPart",2),h([p()],T.prototype,"itemStyle",2),h([p()],T.prototype,"onClickItem",2),T=h([I("docling-table")],T);var yr="1.10.0",xe=["body"],Pe=["title","document_index","section_header","paragraph","table","picture","formula","checkbox_unselected","checkbox_selected","text","list_item","code","reference","page_header","page_footer","key_value_region","empty_value","field_region","field_item","field_key","field_value","field_heading","field_hint","marker","handwritten_text"],br=[...Pe,"footnote","caption","key_value_region","form"];function P(...t){return function(e){return D.DocItem(e)&&t.includes(e.label)}}var Ie={CodeItem:P("code"),FieldHeadingItem:P("field_heading"),FieldItem:P("field_item"),FieldRegionItem:P("field_region"),FieldValueItem:P("field_value"),FormItem:P("form"),FormulaItem:P("formula"),KeyValueItem:P("key_value_region"),ListItem:P("list_item"),PictureItem:P("chart","picture"),SectionHeaderItem:P("section_header"),TableItem:P("document_index","table"),TextItem:P("caption","checkbox_selected","checkbox_unselected","empty_value","field_hint","field_key","footnote","grading_scale","handwritten_text","marker","page_footer","page_header","paragraph","reference","text"),TitleItem:P("title")};function L(...t){return function(e){return t.includes(e.kind)}}var Se={PictureBarChart:L("bar_chart_data"),PictureClassification:L("classification"),PictureDescription:L("description"),PictureMisc:L("misc"),PictureMolecule:L("molecule_data"),PictureLineChart:L("line_chart_data"),PicturePieChart:L("pie_chart_data"),PictureScatterChart:L("scatter_chart_data"),PictureStackedBarChart:L("stacked_bar_chart_data"),PictureTabularChart:L("tabular_chart_data")},D={DocItem(t){return D.NodeItem(t)&&!D.GroupItem(t)},Document(t){return"schema_name"in t&&t.schema_name==="DoclingDocument"},GroupItem(t){return D.NodeItem(t)&&(t.self_ref.startsWith("#/groups/")||t.self_ref==="#/body"||t.self_ref==="#/furniture")},ListGroup(t){return D.GroupItem(t)&&"label"in t&&t.label==="list"},OrderedList(t){return D.GroupItem(t)&&"label"in t&&t.label==="ordered_list"},InlineGroup(t){return D.GroupItem(t)&&"label"in t&&t.label==="inline"},NodeItem(t){return"self_ref"in t},...Se,...Ie};function*te(t,e={}){let r=new Set(e.includedContentLayers??xe);t&&(yield*i(e.root??t.body));function*i(s,a=0){(!D.GroupItem(s)||e.withGroups)&&r.has(s.content_layer??"body")&&(D.DocItem(s)?(e.pageNo===void 0||s.prov?.some(n=>n.page_no===e.pageNo))&&(yield[s,a]):yield[s,a]);let o=D.PictureItem(s),l=new Set(o?(s.captions??[]).map(n=>n.$ref):[]);for(let n of s.children??[]){if(o&&!e.traversePictures&&!l.has(n.$ref))continue;let c=Ce(t,n);D.NodeItem(c)&&(yield*i(c,a+1))}}}function Ce(t,e){return e.$ref.split("/").slice(1).reduce((i,s)=>i[s],t)}globalThis.intextumDocling={components:Qt,iterateDocumentItems:te};
/*! Bundled license information:

@docling/docling-components/dist/index.js:
  (*! Bundled license information:
  
  @lit/reactive-element/node/decorators/custom-element.js:
  @lit/reactive-element/node/decorators/property.js:
  @lit/reactive-element/node/decorators/state.js:
  @lit/reactive-element/node/decorators/event-options.js:
  @lit/reactive-element/node/decorators/base.js:
  @lit/reactive-element/node/decorators/query.js:
  @lit/reactive-element/node/decorators/query-all.js:
  @lit/reactive-element/node/decorators/query-async.js:
  @lit/reactive-element/node/decorators/query-assigned-nodes.js:
  lit-html/node/lit-html.js:
  lit-element/lit-element.js:
  @lit/task/task.js:
    (**
     * @license
     * Copyright 2017 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     *)
  
  @lit-labs/ssr-dom-shim/lib/element-internals.js:
  @lit-labs/ssr-dom-shim/lib/events.js:
    (**
     * @license
     * Copyright 2023 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     *)
  
  @lit-labs/ssr-dom-shim/index.js:
  @lit/reactive-element/node/css-tag.js:
    (**
     * @license
     * Copyright 2019 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     *)
  
  @lit/reactive-element/node/decorators/query-assigned-elements.js:
    (**
     * @license
     * Copyright 2021 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     *)
  
  lit-html/node/is-server.js:
    (**
     * @license
     * Copyright 2022 Google LLC
     * SPDX-License-Identifier: BSD-3-Clause
     *)
  *)
*/
