/*! culfw week program card. Bundles Lit (lit, lit-html, lit-element and
* @lit/reactive-element), BSD-3-Clause, Copyright 2017 Google LLC. The license
* text is in docs/schedule-card.md. */
//#region node_modules/@lit/reactive-element/css-tag.js
var e = globalThis, t = e.ShadowRoot && (e.ShadyCSS === void 0 || e.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, n = Symbol(), r = /* @__PURE__ */ new WeakMap(), i = class {
	constructor(e, t, r) {
		if (this._$cssResult$ = !0, r !== n) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
		this.cssText = e, this.t = t;
	}
	get styleSheet() {
		let e = this.o, n = this.t;
		if (t && e === void 0) {
			let t = n !== void 0 && n.length === 1;
			t && (e = r.get(n)), e === void 0 && ((this.o = e = new CSSStyleSheet()).replaceSync(this.cssText), t && r.set(n, e));
		}
		return e;
	}
	toString() {
		return this.cssText;
	}
}, a = (e) => new i(typeof e == "string" ? e : e + "", void 0, n), o = (e, ...t) => new i(e.length === 1 ? e[0] : t.reduce((t, n, r) => t + ((e) => {
	if (!0 === e._$cssResult$) return e.cssText;
	if (typeof e == "number") return e;
	throw Error("Value passed to 'css' function must be a 'css' function result: " + e + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
})(n) + e[r + 1], e[0]), e, n), s = (n, r) => {
	if (t) n.adoptedStyleSheets = r.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
	else for (let t of r) {
		let r = document.createElement("style"), i = e.litNonce;
		i !== void 0 && r.setAttribute("nonce", i), r.textContent = t.cssText, n.appendChild(r);
	}
}, c = t ? (e) => e : (e) => e instanceof CSSStyleSheet ? ((e) => {
	let t = "";
	for (let n of e.cssRules) t += n.cssText;
	return a(t);
})(e) : e, { is: l, defineProperty: u, getOwnPropertyDescriptor: d, getOwnPropertyNames: ee, getOwnPropertySymbols: te, getPrototypeOf: ne } = Object, f = globalThis, re = f.trustedTypes, ie = re ? re.emptyScript : "", ae = f.reactiveElementPolyfillSupport, p = (e, t) => e, m = {
	toAttribute(e, t) {
		switch (t) {
			case Boolean:
				e = e ? ie : null;
				break;
			case Object:
			case Array: e = e == null ? e : JSON.stringify(e);
		}
		return e;
	},
	fromAttribute(e, t) {
		let n = e;
		switch (t) {
			case Boolean:
				n = e !== null;
				break;
			case Number:
				n = e === null ? null : Number(e);
				break;
			case Object:
			case Array: try {
				n = JSON.parse(e);
			} catch {
				n = null;
			}
		}
		return n;
	}
}, oe = (e, t) => !l(e, t), se = {
	attribute: !0,
	type: String,
	converter: m,
	reflect: !1,
	useDefault: !1,
	hasChanged: oe
};
Symbol.metadata ??= Symbol("metadata"), f.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
var h = class extends HTMLElement {
	static addInitializer(e) {
		this._$Ei(), (this.l ??= []).push(e);
	}
	static get observedAttributes() {
		return this.finalize(), this._$Eh && [...this._$Eh.keys()];
	}
	static createProperty(e, t = se) {
		if (t.state && (t.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(e) && ((t = Object.create(t)).wrapped = !0), this.elementProperties.set(e, t), !t.noAccessor) {
			let n = Symbol(), r = this.getPropertyDescriptor(e, n, t);
			r !== void 0 && u(this.prototype, e, r);
		}
	}
	static getPropertyDescriptor(e, t, n) {
		let { get: r, set: i } = d(this.prototype, e) ?? {
			get() {
				return this[t];
			},
			set(e) {
				this[t] = e;
			}
		};
		return {
			get: r,
			set(t) {
				let a = r?.call(this);
				i?.call(this, t), this.requestUpdate(e, a, n);
			},
			configurable: !0,
			enumerable: !0
		};
	}
	static getPropertyOptions(e) {
		return this.elementProperties.get(e) ?? se;
	}
	static _$Ei() {
		if (this.hasOwnProperty(p("elementProperties"))) return;
		let e = ne(this);
		e.finalize(), e.l !== void 0 && (this.l = [...e.l]), this.elementProperties = new Map(e.elementProperties);
	}
	static finalize() {
		if (this.hasOwnProperty(p("finalized"))) return;
		if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(p("properties"))) {
			let e = this.properties, t = [...ee(e), ...te(e)];
			for (let n of t) this.createProperty(n, e[n]);
		}
		let e = this[Symbol.metadata];
		if (e !== null) {
			let t = litPropertyMetadata.get(e);
			if (t !== void 0) for (let [e, n] of t) this.elementProperties.set(e, n);
		}
		this._$Eh = /* @__PURE__ */ new Map();
		for (let [e, t] of this.elementProperties) {
			let n = this._$Eu(e, t);
			n !== void 0 && this._$Eh.set(n, e);
		}
		this.elementStyles = this.finalizeStyles(this.styles);
	}
	static finalizeStyles(e) {
		let t = [];
		if (Array.isArray(e)) {
			let n = new Set(e.flat(1 / 0).reverse());
			for (let e of n) t.unshift(c(e));
		} else e !== void 0 && t.push(c(e));
		return t;
	}
	static _$Eu(e, t) {
		let n = t.attribute;
		return !1 === n ? void 0 : typeof n == "string" ? n : typeof e == "string" ? e.toLowerCase() : void 0;
	}
	constructor() {
		super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
	}
	_$Ev() {
		this._$ES = new Promise((e) => this.enableUpdating = e), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((e) => e(this));
	}
	addController(e) {
		(this._$EO ??= /* @__PURE__ */ new Set()).add(e), this.renderRoot !== void 0 && this.isConnected && e.hostConnected?.();
	}
	removeController(e) {
		this._$EO?.delete(e);
	}
	_$E_() {
		let e = /* @__PURE__ */ new Map(), t = this.constructor.elementProperties;
		for (let n of t.keys()) this.hasOwnProperty(n) && (e.set(n, this[n]), delete this[n]);
		e.size > 0 && (this._$Ep = e);
	}
	createRenderRoot() {
		let e = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
		return s(e, this.constructor.elementStyles), e;
	}
	connectedCallback() {
		this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((e) => e.hostConnected?.());
	}
	enableUpdating(e) {}
	disconnectedCallback() {
		this._$EO?.forEach((e) => e.hostDisconnected?.());
	}
	attributeChangedCallback(e, t, n) {
		this._$AK(e, n);
	}
	_$ET(e, t) {
		let n = this.constructor.elementProperties.get(e), r = this.constructor._$Eu(e, n);
		if (r !== void 0 && !0 === n.reflect) {
			let i = (n.converter?.toAttribute === void 0 ? m : n.converter).toAttribute(t, n.type);
			this._$Em = e, i == null ? this.removeAttribute(r) : this.setAttribute(r, i), this._$Em = null;
		}
	}
	_$AK(e, t) {
		let n = this.constructor, r = n._$Eh.get(e);
		if (r !== void 0 && this._$Em !== r) {
			let e = n.getPropertyOptions(r), i = typeof e.converter == "function" ? { fromAttribute: e.converter } : e.converter?.fromAttribute === void 0 ? m : e.converter;
			this._$Em = r;
			let a = i.fromAttribute(t, e.type);
			this[r] = a ?? this._$Ej?.get(r) ?? a, this._$Em = null;
		}
	}
	requestUpdate(e, t, n, r = !1, i) {
		if (e !== void 0) {
			let a = this.constructor;
			if (!1 === r && (i = this[e]), n ??= a.getPropertyOptions(e), !((n.hasChanged ?? oe)(i, t) || n.useDefault && n.reflect && i === this._$Ej?.get(e) && !this.hasAttribute(a._$Eu(e, n)))) return;
			this.C(e, t, n);
		}
		!1 === this.isUpdatePending && (this._$ES = this._$EP());
	}
	C(e, t, { useDefault: n, reflect: r, wrapped: i }, a) {
		n && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(e) && (this._$Ej.set(e, a ?? t ?? this[e]), !0 !== i || a !== void 0) || (this._$AL.has(e) || (this.hasUpdated || n || (t = void 0), this._$AL.set(e, t)), !0 === r && this._$Em !== e && (this._$Eq ??= /* @__PURE__ */ new Set()).add(e));
	}
	async _$EP() {
		this.isUpdatePending = !0;
		try {
			await this._$ES;
		} catch (e) {
			Promise.reject(e);
		}
		let e = this.scheduleUpdate();
		return e != null && await e, !this.isUpdatePending;
	}
	scheduleUpdate() {
		return this.performUpdate();
	}
	performUpdate() {
		if (!this.isUpdatePending) return;
		if (!this.hasUpdated) {
			if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
				for (let [e, t] of this._$Ep) this[e] = t;
				this._$Ep = void 0;
			}
			let e = this.constructor.elementProperties;
			if (e.size > 0) for (let [t, n] of e) {
				let { wrapped: e } = n, r = this[t];
				!0 !== e || this._$AL.has(t) || r === void 0 || this.C(t, void 0, n, r);
			}
		}
		let e = !1, t = this._$AL;
		try {
			e = this.shouldUpdate(t), e ? (this.willUpdate(t), this._$EO?.forEach((e) => e.hostUpdate?.()), this.update(t)) : this._$EM();
		} catch (t) {
			throw e = !1, this._$EM(), t;
		}
		e && this._$AE(t);
	}
	willUpdate(e) {}
	_$AE(e) {
		this._$EO?.forEach((e) => e.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(e)), this.updated(e);
	}
	_$EM() {
		this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = !1;
	}
	get updateComplete() {
		return this.getUpdateComplete();
	}
	getUpdateComplete() {
		return this._$ES;
	}
	shouldUpdate(e) {
		return !0;
	}
	update(e) {
		this._$Eq &&= this._$Eq.forEach((e) => this._$ET(e, this[e])), this._$EM();
	}
	updated(e) {}
	firstUpdated(e) {}
};
h.elementStyles = [], h.shadowRootOptions = { mode: "open" }, h[p("elementProperties")] = /* @__PURE__ */ new Map(), h[p("finalized")] = /* @__PURE__ */ new Map(), ae?.({ ReactiveElement: h }), (f.reactiveElementVersions ??= []).push("2.1.2");
//#endregion
//#region node_modules/lit-html/lit-html.js
var g = globalThis, ce = (e) => e, _ = g.trustedTypes, le = _ ? _.createPolicy("lit-html", { createHTML: (e) => e }) : void 0, v = "$lit$", y = `lit$${Math.random().toFixed(9).slice(2)}$`, b = "?" + y, ue = `<${b}>`, x = document, S = () => x.createComment(""), C = (e) => e === null || typeof e != "object" && typeof e != "function", de = Array.isArray, fe = (e) => de(e) || typeof e?.[Symbol.iterator] == "function", w = "[ 	\n\f\r]", T = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, pe = /-->/g, me = />/g, E = RegExp(`>|${w}(?:([^\\s"'>=/]+)(${w}*=${w}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`, "g"), he = /'/g, ge = /"/g, _e = /^(?:script|style|textarea|title)$/i, D = ((e) => (t, ...n) => ({
	_$litType$: e,
	strings: t,
	values: n
}))(1), O = Symbol.for("lit-noChange"), k = Symbol.for("lit-nothing"), ve = /* @__PURE__ */ new WeakMap(), A = x.createTreeWalker(x, 129);
function ye(e, t) {
	if (!de(e) || !e.hasOwnProperty("raw")) throw Error("invalid template strings array");
	return le === void 0 ? t : le.createHTML(t);
}
var be = (e, t) => {
	let n = e.length - 1, r = [], i, a = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", o = T;
	for (let t = 0; t < n; t++) {
		let n = e[t], s, c, l = -1, u = 0;
		for (; u < n.length && (o.lastIndex = u, c = o.exec(n), c !== null);) u = o.lastIndex, o === T ? c[1] === "!--" ? o = pe : c[1] === void 0 ? c[2] === void 0 ? c[3] !== void 0 && (o = E) : (_e.test(c[2]) && (i = RegExp("</" + c[2], "g")), o = E) : o = me : o === E ? c[0] === ">" ? (o = i ?? T, l = -1) : c[1] === void 0 ? l = -2 : (l = o.lastIndex - c[2].length, s = c[1], o = c[3] === void 0 ? E : c[3] === "\"" ? ge : he) : o === ge || o === he ? o = E : o === pe || o === me ? o = T : (o = E, i = void 0);
		let d = o === E && e[t + 1].startsWith("/>") ? " " : "";
		a += o === T ? n + ue : l >= 0 ? (r.push(s), n.slice(0, l) + v + n.slice(l) + y + d) : n + y + (l === -2 ? t : d);
	}
	return [ye(e, a + (e[n] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), r];
}, j = class e {
	constructor({ strings: t, _$litType$: n }, r) {
		let i;
		this.parts = [];
		let a = 0, o = 0, s = t.length - 1, c = this.parts, [l, u] = be(t, n);
		if (this.el = e.createElement(l, r), A.currentNode = this.el.content, n === 2 || n === 3) {
			let e = this.el.content.firstChild;
			e.replaceWith(...e.childNodes);
		}
		for (; (i = A.nextNode()) !== null && c.length < s;) {
			if (i.nodeType === 1) {
				if (i.hasAttributes()) for (let e of i.getAttributeNames()) if (e.endsWith(v)) {
					let t = u[o++], n = i.getAttribute(e).split(y), r = /([.?@])?(.*)/.exec(t);
					c.push({
						type: 1,
						index: a,
						name: r[2],
						strings: n,
						ctor: r[1] === "." ? Se : r[1] === "?" ? Ce : r[1] === "@" ? we : P
					}), i.removeAttribute(e);
				} else e.startsWith(y) && (c.push({
					type: 6,
					index: a
				}), i.removeAttribute(e));
				if (_e.test(i.tagName)) {
					let e = i.textContent.split(y), t = e.length - 1;
					if (t > 0) {
						i.textContent = _ ? _.emptyScript : "";
						for (let n = 0; n < t; n++) i.append(e[n], S()), A.nextNode(), c.push({
							type: 2,
							index: ++a
						});
						i.append(e[t], S());
					}
				}
			} else if (i.nodeType === 8) {
				if (i.data === b) c.push({
					type: 2,
					index: a
				});
				else {
					let e = -1;
					for (; (e = i.data.indexOf(y, e + 1)) !== -1;) c.push({
						type: 7,
						index: a
					}), e += y.length - 1;
				}
			}
			a++;
		}
	}
	static createElement(e, t) {
		let n = x.createElement("template");
		return n.innerHTML = e, n;
	}
};
function M(e, t, n = e, r) {
	if (t === O) return t;
	let i = r === void 0 ? n._$Cl : n._$Co?.[r], a = C(t) ? void 0 : t._$litDirective$;
	return i?.constructor !== a && (i?._$AO?.(!1), a === void 0 ? i = void 0 : (i = new a(e), i._$AT(e, n, r)), r === void 0 ? n._$Cl = i : (n._$Co ??= [])[r] = i), i !== void 0 && (t = M(e, i._$AS(e, t.values), i, r)), t;
}
var xe = class {
	constructor(e, t) {
		this._$AV = [], this._$AN = void 0, this._$AD = e, this._$AM = t;
	}
	get parentNode() {
		return this._$AM.parentNode;
	}
	get _$AU() {
		return this._$AM._$AU;
	}
	u(e) {
		let { el: { content: t }, parts: n } = this._$AD, r = (e?.creationScope ?? x).importNode(t, !0);
		A.currentNode = r;
		let i = A.nextNode(), a = 0, o = 0, s = n[0];
		for (; s !== void 0;) {
			if (a === s.index) {
				let t;
				s.type === 2 ? t = new N(i, i.nextSibling, this, e) : s.type === 1 ? t = new s.ctor(i, s.name, s.strings, this, e) : s.type === 6 && (t = new Te(i, this, e)), this._$AV.push(t), s = n[++o];
			}
			a !== s?.index && (i = A.nextNode(), a++);
		}
		return A.currentNode = x, r;
	}
	p(e) {
		let t = 0;
		for (let n of this._$AV) n !== void 0 && (n.strings === void 0 ? n._$AI(e[t]) : (n._$AI(e, n, t), t += n.strings.length - 2)), t++;
	}
}, N = class e {
	get _$AU() {
		return this._$AM?._$AU ?? this._$Cv;
	}
	constructor(e, t, n, r) {
		this.type = 2, this._$AH = k, this._$AN = void 0, this._$AA = e, this._$AB = t, this._$AM = n, this.options = r, this._$Cv = r?.isConnected ?? !0;
	}
	get parentNode() {
		let e = this._$AA.parentNode, t = this._$AM;
		return t !== void 0 && e?.nodeType === 11 && (e = t.parentNode), e;
	}
	get startNode() {
		return this._$AA;
	}
	get endNode() {
		return this._$AB;
	}
	_$AI(e, t = this) {
		e = M(this, e, t), C(e) ? e === k || e == null || e === "" ? (this._$AH !== k && this._$AR(), this._$AH = k) : e !== this._$AH && e !== O && this._(e) : e._$litType$ === void 0 ? e.nodeType === void 0 ? fe(e) ? this.k(e) : this._(e) : this.T(e) : this.$(e);
	}
	O(e) {
		return this._$AA.parentNode.insertBefore(e, this._$AB);
	}
	T(e) {
		this._$AH !== e && (this._$AR(), this._$AH = this.O(e));
	}
	_(e) {
		this._$AH !== k && C(this._$AH) ? this._$AA.nextSibling.data = e : this.T(x.createTextNode(e)), this._$AH = e;
	}
	$(e) {
		let { values: t, _$litType$: n } = e, r = typeof n == "number" ? this._$AC(e) : (n.el === void 0 && (n.el = j.createElement(ye(n.h, n.h[0]), this.options)), n);
		if (this._$AH?._$AD === r) this._$AH.p(t);
		else {
			let e = new xe(r, this), n = e.u(this.options);
			e.p(t), this.T(n), this._$AH = e;
		}
	}
	_$AC(e) {
		let t = ve.get(e.strings);
		return t === void 0 && ve.set(e.strings, t = new j(e)), t;
	}
	k(t) {
		de(this._$AH) || (this._$AH = [], this._$AR());
		let n = this._$AH, r, i = 0;
		for (let a of t) i === n.length ? n.push(r = new e(this.O(S()), this.O(S()), this, this.options)) : r = n[i], r._$AI(a), i++;
		i < n.length && (this._$AR(r && r._$AB.nextSibling, i), n.length = i);
	}
	_$AR(e = this._$AA.nextSibling, t) {
		for (this._$AP?.(!1, !0, t); e !== this._$AB;) {
			let t = ce(e).nextSibling;
			ce(e).remove(), e = t;
		}
	}
	setConnected(e) {
		this._$AM === void 0 && (this._$Cv = e, this._$AP?.(e));
	}
}, P = class {
	get tagName() {
		return this.element.tagName;
	}
	get _$AU() {
		return this._$AM._$AU;
	}
	constructor(e, t, n, r, i) {
		this.type = 1, this._$AH = k, this._$AN = void 0, this.element = e, this.name = t, this._$AM = r, this.options = i, n.length > 2 || n[0] !== "" || n[1] !== "" ? (this._$AH = Array(n.length - 1).fill(/* @__PURE__ */ new String()), this.strings = n) : this._$AH = k;
	}
	_$AI(e, t = this, n, r) {
		let i = this.strings, a = !1;
		if (i === void 0) e = M(this, e, t, 0), a = !C(e) || e !== this._$AH && e !== O, a && (this._$AH = e);
		else {
			let r = e, o, s;
			for (e = i[0], o = 0; o < i.length - 1; o++) s = M(this, r[n + o], t, o), s === O && (s = this._$AH[o]), a ||= !C(s) || s !== this._$AH[o], s === k ? e = k : e !== k && (e += (s ?? "") + i[o + 1]), this._$AH[o] = s;
		}
		a && !r && this.j(e);
	}
	j(e) {
		e === k ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, e ?? "");
	}
}, Se = class extends P {
	constructor() {
		super(...arguments), this.type = 3;
	}
	j(e) {
		this.element[this.name] = e === k ? void 0 : e;
	}
}, Ce = class extends P {
	constructor() {
		super(...arguments), this.type = 4;
	}
	j(e) {
		this.element.toggleAttribute(this.name, !!e && e !== k);
	}
}, we = class extends P {
	constructor(e, t, n, r, i) {
		super(e, t, n, r, i), this.type = 5;
	}
	_$AI(e, t = this) {
		if ((e = M(this, e, t, 0) ?? k) === O) return;
		let n = this._$AH, r = e === k && n !== k || e.capture !== n.capture || e.once !== n.once || e.passive !== n.passive, i = e !== k && (n === k || r);
		r && this.element.removeEventListener(this.name, this, n), i && this.element.addEventListener(this.name, this, e), this._$AH = e;
	}
	handleEvent(e) {
		typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, e) : this._$AH.handleEvent(e);
	}
}, Te = class {
	constructor(e, t, n) {
		this.element = e, this.type = 6, this._$AN = void 0, this._$AM = t, this.options = n;
	}
	get _$AU() {
		return this._$AM._$AU;
	}
	_$AI(e) {
		M(this, e);
	}
}, Ee = {
	M: v,
	P: y,
	A: b,
	C: 1,
	L: be,
	R: xe,
	D: fe,
	V: M,
	I: N,
	H: P,
	N: Ce,
	U: we,
	B: Se,
	F: Te
}, De = g.litHtmlPolyfillSupport;
De?.(j, N), (g.litHtmlVersions ??= []).push("3.3.3");
var Oe = (e, t, n) => {
	let r = n?.renderBefore ?? t, i = r._$litPart$;
	if (i === void 0) {
		let e = n?.renderBefore ?? null;
		r._$litPart$ = i = new N(t.insertBefore(S(), e), e, void 0, n ?? {});
	}
	return i._$AI(e), i;
}, F = globalThis, I = class extends h {
	constructor() {
		super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
	}
	createRenderRoot() {
		let e = super.createRenderRoot();
		return this.renderOptions.renderBefore ??= e.firstChild, e;
	}
	update(e) {
		let t = this.render();
		this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(e), this._$Do = Oe(t, this.renderRoot, this.renderOptions);
	}
	connectedCallback() {
		super.connectedCallback(), this._$Do?.setConnected(!0);
	}
	disconnectedCallback() {
		super.disconnectedCallback(), this._$Do?.setConnected(!1);
	}
	render() {
		return O;
	}
};
I._$litElement$ = !0, I.finalized = !0, F.litElementHydrateSupport?.({ LitElement: I });
var ke = F.litElementPolyfillSupport;
ke?.({ LitElement: I }), (F.litElementVersions ??= []).push("4.2.2");
//#endregion
//#region node_modules/lit-html/directive.js
var L = {
	ATTRIBUTE: 1,
	CHILD: 2,
	PROPERTY: 3,
	BOOLEAN_ATTRIBUTE: 4,
	EVENT: 5,
	ELEMENT: 6
}, Ae = (e) => (...t) => ({
	_$litDirective$: e,
	values: t
}), je = class {
	constructor(e) {}
	get _$AU() {
		return this._$AM._$AU;
	}
	_$AT(e, t, n) {
		this._$Ct = e, this._$AM = t, this._$Ci = n;
	}
	_$AS(e, t) {
		return this.update(e, t);
	}
	update(e, t) {
		return this.render(...t);
	}
}, { I: Me } = Ee, Ne = (e) => e.strings === void 0, Pe = {}, Fe = (e, t = Pe) => e._$AH = t, Ie = Ae(class extends je {
	constructor(e) {
		if (super(e), e.type !== L.PROPERTY && e.type !== L.ATTRIBUTE && e.type !== L.BOOLEAN_ATTRIBUTE) throw Error("The `live` directive is not allowed on child or event bindings");
		if (!Ne(e)) throw Error("`live` bindings can only contain a single expression");
	}
	render(e) {
		return e;
	}
	update(e, [t]) {
		if (t === O || t === k) return t;
		let n = e.element, r = e.name;
		if (e.type === L.PROPERTY) {
			if (t === n[r]) return O;
		} else if (e.type === L.BOOLEAN_ATTRIBUTE) {
			if (!!t === n.hasAttribute(r)) return O;
		} else if (e.type === L.ATTRIBUTE && n.getAttribute(r) === t + "") return O;
		return Fe(e), t;
	}
}), R = [
	"monday",
	"tuesday",
	"wednesday",
	"thursday",
	"friday",
	"saturday",
	"sunday"
], z = 60, Le = 60, Re = 360, ze = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
function B(e, t = 1440) {
	let n = ze.exec(e.trim());
	if (n === null) return null;
	let r = Number(n[1]), i = Number(n[2]), a = Number(n[3] ?? 0), o = r * z + i;
	return i >= z || a !== 0 || o > t ? null : o;
}
function V(e) {
	let t = Math.floor(e / z), n = e % z;
	return `${String(t).padStart(2, "0")}:${String(n).padStart(2, "0")}`;
}
function H(e, t, n) {
	return Math.min(Math.max(e, t), n);
}
function U(e, t) {
	let n = t.stepMinutes;
	return H(Math.round(e / n) * n, 0, t.dayEnd);
}
function W(e) {
	return e.map((e) => ({ ...e })).sort((e, t) => e.start - t.start || e.end - t.end);
}
function Be(e, t) {
	if (e.length !== t.length) return !1;
	let n = W(e), r = W(t);
	return n.every((e, t) => e.start === r[t]?.start && e.end === r[t]?.end);
}
function G(e, t = {}) {
	return {
		key: e,
		params: t
	};
}
function Ve(e, t) {
	return G("schedule_too_many_ranges", {
		count: String(e),
		max_ranges: String(t.maxPeriods)
	});
}
function He(e, t) {
	for (let [n, r] of e) {
		if (n === null || !Number.isInteger(n) || n < 0 || n > t.dayEnd) return G("schedule_time_invalid", { value: r });
		if (n % t.stepMinutes !== 0) return G("schedule_time_step", {
			value: r,
			step: String(t.stepMinutes)
		});
	}
	return null;
}
function Ue(e, t) {
	if (e.length > t.maxPeriods) return Ve(e.length, t);
	for (let n of e) {
		let e = He([[n.start, V(n.start)], [n.end, V(n.end)]], t);
		if (e !== null) return e;
	}
	for (let t of e) if (t.start >= t.end) return G("schedule_range_backwards", {
		start: V(t.start),
		end: V(t.end)
	});
	let n = W(e);
	for (let e = 1; e < n.length; e += 1) {
		let t = n[e - 1], r = n[e];
		if (r.start < t.end) return G("schedule_ranges_overlap", {
			first_start: V(t.start),
			first_end: V(t.end),
			second_start: V(r.start),
			second_end: V(r.end)
		});
	}
	return null;
}
function We(e) {
	let t = W(e);
	return t.some((e, n) => n > 0 && t[n - 1]?.end === e.start);
}
function Ge(e) {
	let t = [];
	for (let n of W(e)) {
		let e = t[t.length - 1];
		e !== void 0 && e.end >= n.start ? e.end = Math.max(e.end, n.end) : t.push(n);
	}
	return t;
}
function Ke(e, t) {
	let n = [], r = 0;
	for (let i of W(e)) i.start - r >= t.stepMinutes && n.push({
		start: r,
		end: i.start
	}), r = Math.max(r, i.end);
	return t.dayEnd - r >= t.stepMinutes && n.push({
		start: r,
		end: t.dayEnd
	}), n;
}
function qe(e, t) {
	return W([...e, t]);
}
function Je(e, t, n) {
	if (e.length >= n.maxPeriods) return null;
	let r = U(t, n), i = Ke(e, n).find((e) => e.start <= r && r < e.end);
	if (i === void 0) return null;
	let a = Math.min(r, i.end - n.stepMinutes);
	return qe(e, {
		start: a,
		end: Math.min(a + Le, i.end)
	});
}
function Ye(e, t) {
	if (e.length >= t.maxPeriods) return null;
	let n;
	for (let r of Ke(e, t)) (n === void 0 || r.end - r.start > n.end - n.start) && (n = r);
	if (n === void 0) return null;
	let r = n.start === 0 && n.end >= 420 ? Re : n.start;
	return qe(e, {
		start: r,
		end: Math.min(r + Le, n.end)
	});
}
function K(e, t, n) {
	return {
		low: e[t - 1]?.end ?? 0,
		high: e[t + 1]?.start ?? n.dayEnd
	};
}
function Xe(e, t, n, r) {
	let i = e[t];
	if (i === void 0) return e.map((e) => ({ ...e }));
	let a = i.end - i.start, { low: o, high: s } = K(e, t, r), c = H(U(n, r), o, s - a);
	return e.map((e, n) => n === t ? {
		start: c,
		end: c + a
	} : { ...e });
}
function q(e, t, n, r) {
	let i = e[t];
	if (i === void 0) return e.map((e) => ({ ...e }));
	let { low: a } = K(e, t, r), o = H(U(n, r), a, i.end - r.stepMinutes);
	return e.map((e, n) => n === t ? {
		start: o,
		end: e.end
	} : { ...e });
}
function Ze(e, t, n, r) {
	let i = e[t];
	if (i === void 0) return e.map((e) => ({ ...e }));
	let { high: a } = K(e, t, r), o = H(U(n, r), i.start + r.stepMinutes, a);
	return e.map((e, n) => n === t ? {
		start: e.start,
		end: o
	} : { ...e });
}
function Qe(e, t) {
	return e.filter((e, n) => n !== t).map((e) => ({ ...e }));
}
function J(e) {
	return e.requested ?? e.periods;
}
function Y(e, t) {
	return R.filter((n) => {
		let r = e[n];
		if (r === void 0) return !1;
		let i = J(t[n]);
		return i === null || !Be(r, i);
	});
}
function $e(e, t) {
	return (e === "weekdays" ? R.slice(0, 5) : e === "weekend" ? R.slice(5) : R).filter((e) => e !== t);
}
function et(e, t) {
	let n = {};
	for (let r of t) n[r] = W(e[r] ?? []).map((e) => ({
		start: V(e.start),
		end: V(e.end)
	}));
	return n;
}
//#endregion
//#region src/day-track.ts
var tt = 60, nt = 6, rt = class extends I {
	static {
		this.properties = {
			limits: { attribute: !1 },
			step: { type: Number }
		};
	}
	constructor() {
		super(), this.limits = {
			stepMinutes: 10,
			maxPeriods: 2,
			dayEnd: 1440
		}, this.step = 360;
	}
	static {
		this.styles = o`
    :host {
      display: block;
    }
    .axis {
      position: relative;
      height: 1.2em;
      margin-block-end: 2px;
      font-size: var(--ha-font-size-xs, 0.75rem);
      color: var(--secondary-text-color);
      direction: ltr;
    }
    .tick {
      position: absolute;
      transform: translateX(-50%);
      white-space: nowrap;
    }
    .tick:first-child {
      transform: none;
    }
    .tick:last-child {
      transform: translateX(-100%);
    }
  `;
	}
	render() {
		let e = [];
		for (let t = 0; t <= this.limits.dayEnd; t += this.step) e.push(t);
		return D`<div class="axis" aria-hidden="true">
      ${e.map((e) => D`<span class="tick" style="left:${e / this.limits.dayEnd * 100}%"
            >${String(e / 60).padStart(2, "0")}</span
          >`)}
    </div>`;
	}
}, it = class extends I {
	static {
		this.properties = {
			periods: { attribute: !1 },
			limits: { attribute: !1 },
			labeler: { attribute: !1 },
			interactive: { type: Boolean },
			large: { type: Boolean },
			unknown: { type: Boolean },
			pending: { type: Boolean },
			axis: { type: Boolean },
			axisStep: {
				type: Number,
				attribute: "axis-step"
			},
			trackLabel: {
				type: String,
				attribute: "track-label"
			},
			_bubble: { state: !0 }
		};
	}
	constructor() {
		super(), this._drag = null, this.periods = [], this.limits = {
			stepMinutes: 10,
			maxPeriods: 2,
			dayEnd: 1440
		}, this.labeler = (e, t) => `${e} ${t + 1}`, this.interactive = !1, this.large = !1, this.unknown = !1, this.pending = !1, this.axis = !1, this.axisStep = 360, this.trackLabel = "", this._bubble = null;
	}
	static {
		this.styles = o`
    :host {
      display: block;
      --handle-in: 6px;
      --handle-out: 10px;
      --track-height: 28px;
      touch-action: pan-y;
    }
    :host([large]) {
      --handle-in: 8px;
      --handle-out: 36px;
      --track-height: 60px;
    }
    .track {
      position: relative;
      height: var(--track-height);
      direction: ltr;
      border-radius: var(--ha-border-radius-sm, 4px);
      background: var(--secondary-background-color, rgba(127, 127, 127, 0.15));
      outline: 1px solid var(--divider-color, rgba(127, 127, 127, 0.4));
      outline-offset: -1px;
      touch-action: pan-y;
      user-select: none;
      -webkit-user-select: none;
    }
    .track.unknown {
      background-image: repeating-linear-gradient(
        135deg,
        transparent 0 6px,
        var(--divider-color, rgba(127, 127, 127, 0.4)) 6px 8px
      );
    }
    .unknown-mark {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      font-size: var(--ha-font-size-s, 0.875rem);
      color: var(--secondary-text-color);
      pointer-events: none;
    }
    .gridline {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 1px;
      background: var(--divider-color, rgba(127, 127, 127, 0.4));
      opacity: 0.5;
      pointer-events: none;
    }
    .bar:focus-visible {
      outline: 2px solid var(--ha-color-focus, var(--primary-text-color));
      outline-offset: 2px;
    }
    .bar {
      position: absolute;
      top: 3px;
      bottom: 3px;
      min-width: 3px;
      box-sizing: border-box;
      border-radius: var(--ha-border-radius-sm, 4px);
      background: var(--primary-color);
      border: 2px solid var(--primary-color);
      touch-action: pan-y;
    }
    .interactive .bar {
      cursor: grab;
    }
    .pending .bar {
      background-image: repeating-linear-gradient(
        135deg,
        transparent 0 5px,
        var(--card-background-color, #fff) 5px 7px
      );
    }
    .handle {
      position: absolute;
      top: 0;
      bottom: 0;
      width: calc(var(--handle-in) + var(--handle-out));
      display: flex;
      align-items: center;
      touch-action: none;
      cursor: ew-resize;
      z-index: 2;
    }
    /* The hit area reaches mostly outside of the bar, so that the middle of a
       short bar stays free for moving it with a finger. */
    .handle.start {
      transform: translateX(calc(-1 * var(--handle-out)));
    }
    .handle.end {
      transform: translateX(calc(-1 * var(--handle-in)));
    }
    .handle::before {
      content: "";
      width: 6px;
      height: 70%;
      border-radius: 3px;
      background: var(--text-primary-color, #fff);
      border: 1px solid var(--primary-color);
      box-sizing: border-box;
    }
    .handle.start::before {
      margin-inline-start: calc(var(--handle-out) - 3px);
    }
    .handle.end::before {
      margin-inline-start: calc(var(--handle-in) - 3px);
    }
    .handle:focus-visible {
      outline: 2px solid var(--ha-color-focus, var(--primary-text-color));
      outline-offset: 1px;
    }
    .handle:focus-visible::before,
    .handle.active::before {
      background: var(--primary-text-color);
    }
    .bubble {
      position: absolute;
      bottom: calc(100% + 6px);
      transform: translateX(-50%);
      padding: 2px 8px;
      border-radius: var(--ha-border-radius-md, 8px);
      background: var(--primary-text-color);
      color: var(--card-background-color, #fff);
      font-size: var(--ha-font-size-m, 1rem);
      font-variant-numeric: tabular-nums;
      pointer-events: none;
      white-space: nowrap;
      z-index: 3;
    }
    :host([large]) .bubble {
      bottom: calc(100% + 28px);
      font-size: 1.25rem;
      padding: 4px 12px;
    }
  `;
	}
	updated(e) {
		e.has("large") && this.toggleAttribute("large", this.large);
	}
	get _track() {
		return this.renderRoot.querySelector(".track");
	}
	_minuteAt(e) {
		let t = this._track.getBoundingClientRect();
		return (e - t.left) / t.width * this.limits.dayEnd;
	}
	_percent(e) {
		return `${e / this.limits.dayEnd * 100}%`;
	}
	_emit(e) {
		this.dispatchEvent(new CustomEvent("periods-change", {
			detail: { periods: e },
			bubbles: !0,
			composed: !0
		}));
	}
	_begin(e, t, n, r) {
		!this.interactive || e.pointerType === "mouse" && e.button !== 0 || (this._drag = {
			kind: t,
			index: n,
			pointerId: e.pointerId,
			startX: e.clientX,
			origin: this.periods.map((e) => ({ ...e })),
			grab: r,
			moved: !1
		}, e.currentTarget.setPointerCapture(e.pointerId));
	}
	_onHandleDown(e, t, n) {
		e.stopPropagation();
		let r = this.periods[t], i = n === "start" ? r.start : r.end;
		this._begin(e, n, t, i - this._minuteAt(e.clientX)), this._drag !== null && (this._drag.moved = !0, this._bubble = { minute: i });
	}
	_onBarDown(e, t) {
		e.stopPropagation();
		let n = this.periods[t];
		this._begin(e, "move", t, n.start - this._minuteAt(e.clientX));
	}
	_onTrackDown(e) {
		this._begin(e, "create", -1, 0);
	}
	_onMove(e) {
		let t = this._drag;
		if (t === null || e.pointerId !== t.pointerId) return;
		if (!t.moved) {
			if (Math.abs(e.clientX - t.startX) < nt) return;
			t.moved = !0;
		}
		if (t.kind === "create") return;
		let n = this._minuteAt(e.clientX) + t.grab, r = this.limits, i;
		i = t.kind === "start" ? q(t.origin, t.index, n, r) : t.kind === "end" ? Ze(t.origin, t.index, n, r) : Xe(t.origin, t.index, n, r);
		let a = i[t.index];
		this._bubble = { minute: t.kind === "end" ? a.end : a.start }, JSON.stringify(i) !== JSON.stringify(this.periods) && this._emit(i);
	}
	_onUp(e) {
		let t = this._drag;
		if (t !== null && e.pointerId === t.pointerId && (this._drag = null, this._bubble = null, t.kind === "create" && !t.moved)) {
			let t = Je(this.periods, this._minuteAt(e.clientX), this.limits);
			t !== null && this._emit(t);
		}
	}
	_onCancel(e) {
		let t = this._drag;
		t !== null && e.pointerId === t.pointerId && (this._drag = null, this._bubble = null, t.moved && t.kind !== "create" && this._emit(t.origin));
	}
	_onKey(e, t, n) {
		let r = this.periods[t];
		if (r === void 0) return;
		let i = this.limits, a = n === "end" ? r.end : r.start, o = e.shiftKey ? tt : i.stepMinutes, s;
		switch (e.key) {
			case "ArrowLeft":
			case "ArrowDown":
				s = a - o;
				break;
			case "ArrowRight":
			case "ArrowUp":
				s = a + o;
				break;
			case "Home":
				s = 0;
				break;
			case "End":
				s = i.dayEnd;
				break;
			case "Delete":
			case "Backspace":
				e.preventDefault(), this._emit(Qe(this.periods, t)), setTimeout(() => this._focusAny(), 0);
				return;
			default: return;
		}
		e.preventDefault();
		let c;
		c = n === "start" ? q(this.periods, t, s, i) : n === "end" ? Ze(this.periods, t, s, i) : Xe(this.periods, t, s, i), JSON.stringify(c) !== JSON.stringify(this.periods) && this._emit(c);
	}
	_focusAny() {
		(this.renderRoot.querySelector(".handle") ?? this._track).focus();
	}
	render() {
		let e = this.interactive;
		return D`
      ${this.axis ? D`<fht-time-axis .limits=${this.limits} .step=${this.axisStep}></fht-time-axis>` : k}
      <div
        class="track ${e ? "interactive" : ""} ${this.unknown ? "unknown" : ""} ${this.pending ? "pending" : ""}"
        tabindex=${e && this.periods.length === 0 ? "-1" : k}
        role=${e ? "group" : k}
        aria-label=${e ? this.trackLabel : k}
        aria-hidden=${e ? k : "true"}
        @pointerdown=${(e) => this._onTrackDown(e)}
        @pointermove=${(e) => this._onMove(e)}
        @pointerup=${(e) => this._onUp(e)}
        @pointercancel=${(e) => this._onCancel(e)}
      >
        ${this._gridlines()}
        ${this.unknown && this.periods.length === 0 ? D`<span class="unknown-mark">?</span>` : k}
        ${this.periods.map((t, n) => this._renderBar(t, n, e))}
        ${this._bubble === null ? k : D`<span
                class="bubble"
                style="left:${this._percent(H(this._bubble.minute, 0, this.limits.dayEnd))}"
                >${V(this._bubble.minute)}</span
              >`}
      </div>
    `;
	}
	_gridlines() {
		let e = [];
		for (let t = this.axisStep; t < this.limits.dayEnd; t += this.axisStep) e.push(t);
		return e.map((e) => D`<span class="gridline" style="left:${this._percent(e)}"></span>`);
	}
	_renderBar(e, t, n) {
		let { limits: r } = this, i = this.periods[t - 1]?.end ?? 0, a = this.periods[t + 1]?.start ?? r.dayEnd, o = e.end - e.start;
		return D`
      <div
        class="bar"
        style="left:${this._percent(e.start)};width:${this._percent(o)}"
        role=${n ? "slider" : k}
        tabindex=${n ? "0" : k}
        aria-label=${n ? this.labeler("move", t) : k}
        aria-orientation=${n ? "horizontal" : k}
        aria-valuemin=${n ? i : k}
        aria-valuemax=${n ? a - o : k}
        aria-valuenow=${n ? e.start : k}
        aria-valuetext=${n ? `${V(e.start)}–${V(e.end)}` : k}
        @pointerdown=${(e) => this._onBarDown(e, t)}
        @keydown=${(e) => this._onKey(e, t, "move")}
      ></div>
      ${n ? D`${this._renderHandle(e, t, "start", this.labeler)}${this._renderHandle(e, t, "end", this.labeler)}` : k}
    `;
	}
	_renderHandle(e, t, n, r) {
		let i = n === "start" ? e.start : e.end, { limits: a } = this, o = this.periods[t - 1]?.end ?? 0, s = this.periods[t + 1]?.start ?? a.dayEnd, c = n === "start" ? o : e.start + a.stepMinutes, l = n === "start" ? e.end - a.stepMinutes : s, u = `left:${this._percent(i)}`;
		return D`<div
      class="handle ${n} ${this._drag?.index === t && this._drag.kind === n ? "active" : ""}"
      role="slider"
      tabindex="0"
      style=${u}
      aria-label=${r(n, t)}
      aria-orientation="horizontal"
      aria-valuemin=${c}
      aria-valuemax=${l}
      aria-valuenow=${i}
      aria-valuetext=${V(i)}
      @pointerdown=${(e) => this._onHandleDown(e, t, n)}
      @keydown=${(e) => this._onKey(e, t, n)}
    ></div>`;
	}
};
customElements.get("fht-time-axis") || customElements.define("fht-time-axis", rt), customElements.get("fht-day-track") || customElements.define("fht-day-track", it);
//#endregion
//#region src/i18n.ts
var at = {
	"card.title": "Week program",
	"card.stateUnknown": "Thermostat {entity} was not found.",
	"card.loading": "Loading the week program…",
	"temp.day": "Day",
	"temp.night": "Night",
	"temp.unknown": "unknown",
	"reach.ok": "Thermostat reachable",
	"reach.silent": "Thermostat not responding",
	"reach.link": "Radio stick disconnected",
	"reach.queueHint": "Changes wait in the queue and are sent when the thermostat answers.",
	"reach.linkHint": "Changes wait in the queue and are sent when the radio stick is back.",
	"status.unknown": "Not read",
	"status.saved": "Saved",
	"status.queued": "Queued",
	"status.sending": "Sending",
	"status.unconfirmed": "Not confirmed",
	"status.error": "Error",
	"status.edited": "Edited",
	"action.save": "Save",
	"action.saveCount": "Save ({count})",
	"action.discard": "Discard",
	"action.read": "Read now",
	"action.readWeek": "Read week",
	"action.readDay": "Read this day",
	"action.resend": "Send again",
	"action.editEmpty": "Edit an empty program",
	"action.copy": "Copy to other days…",
	"action.clear": "Clear day",
	"action.reset": "Reset day",
	"action.add": "Add heating period",
	"action.remove": "Remove",
	"action.merge": "Merge touching periods",
	"action.back": "Back to the week",
	"action.cancel": "Cancel",
	"action.copyApply": "Copy",
	"action.overwrite": "Overwrite",
	"action.retry": "Try again",
	"action.dismiss": "Dismiss",
	"preset.weekdays": "Weekdays",
	"preset.weekend": "Weekend",
	"preset.all": "All days",
	"empty.title": "The week program has not been read yet.",
	"empty.body": "The thermostat sends it in 28 radio telegrams, so reading the whole week takes about 35 minutes.",
	"empty.requested": "Reading was requested. The days appear here as the thermostat reports them.",
	"load.error": "The week program could not be loaded: {message}",
	"list.noHeating": "Night temperature all day",
	"list.unknown": "Not read yet",
	"legend.heating": "Heating period (day temperature)",
	"legend.night": "Night temperature",
	"legend.unknown": "Not read",
	"legend.pending": "On its way",
	"footer.clean": "No changes.",
	"footer.changed": "{count, plural, one {# day changed} other {# days changed}}",
	"footer.hint": "Each day takes about 2 minutes to reach the thermostat.",
	"day.unknownHint": "This day was never read. Saving replaces the whole day in the thermostat.",
	"day.pendingHint": "This day is on its way to the thermostat.",
	"day.editor": "Edit {day}",
	"field.start": "Start",
	"field.end": "End",
	"field.period": "Period {n}",
	"field.earlier": "10 minutes earlier",
	"field.later": "10 minutes later",
	"aria.start": "{day}, period {n}, start",
	"aria.end": "{day}, period {n}, end",
	"aria.move": "{day}, period {n}, move",
	"aria.track": "{day}, heating periods",
	"aria.row": "{day}: {summary}, {status}",
	"aria.startField": "{day}, period {n}, start time",
	"aria.endField": "{day}, period {n}, end time",
	"aria.startEarlier": "{day}, period {n}, start 10 minutes earlier",
	"aria.startLater": "{day}, period {n}, start 10 minutes later",
	"aria.endEarlier": "{day}, period {n}, end 10 minutes earlier",
	"aria.endLater": "{day}, period {n}, end 10 minutes later",
	"aria.remove": "{day}, remove period {n}",
	"announce.sent": "Sent to the thermostat: {days}.",
	"announce.unchanged": "Already up to date: {days}.",
	"announce.read": "Reading was requested.",
	"announce.discarded": "Changes discarded.",
	"announce.copied": "Copied to {days}.",
	"copy.title": "Copy {day} to other days",
	"copy.body": "The copies are changes that you still have to save.",
	"confirm.title": "Overwrite days that were never read?",
	"confirm.body": "The days {days} were never read from the thermostat. Saving replaces them completely.",
	"error.save": "Saving failed: {message}",
	"error.read": "Reading failed: {message}",
	"error.unauthorized": "You are not allowed to change this thermostat.",
	"error.unsupported": "The integration does not know the week program commands. Update the integration and reload the page.",
	"error.unknown": "Something went wrong.",
	"error.invalid": "The data from Home Assistant has an unexpected form.",
	"err.schedule_time_invalid": "{day}: {value} is not a time of day. Write it as HH:MM, for example 06:30, and use 24:00 for the end of the day.",
	"err.schedule_time_step": "{day}: {value} is not a multiple of {step} minutes. The thermostat switches in steps of {step} minutes.",
	"err.schedule_too_many_ranges": "{day}: {count} time ranges are too many. The thermostat takes at most {max_ranges} ranges per day.",
	"err.schedule_range_backwards": "{day}: the range from {start} to {end} must end after it starts. Use 24:00 for midnight at the end of the day.",
	"err.schedule_ranges_overlap": "{day}: the ranges from {first_start} to {first_end} and from {second_start} to {second_end} overlap.",
	"err.schedule_partly_sent": "Only part of the week program was sent. The days {sent} are on their way, and the days {unsent} were not sent. Set those days again.",
	"err.schedule_entity_unknown": "{entity_id} is not the climate entity of a thermostat of this integration.",
	"err.send_unknown_device": "The thermostat {code} has not been heard yet, so nothing can be sent to it. Wait until it transmits, which can take a few minutes.",
	"err.send_device_silent": "The thermostat {code} has been silent for {minutes} minutes, so it would never collect the command. Check its batteries and its distance to the radio stick.",
	"err.send_device_unconfirmed": "The thermostat {code} never echoed a command of this radio stick, so nothing is sent to it on its own.",
	"err.send_device_unresponsive": "The thermostat {code} did not echo the last messages, so only commands that you ask for are sent to it.",
	"err.send_not_connected": "The radio stick is not connected, its state is {state}. It connects again automatically.",
	"err.send_no_credit": "The 1% radio budget is used up. It has {credit} ms left and needs {minimum} ms. Try again in a few minutes.",
	"err.send_credit_exhausted": "The 1% radio budget stayed below {minimum} ms for {minutes} minutes, so the command was not sent. Try again in a few minutes.",
	"err.send_buffer_full": "The buffer of the radio stick has {free} bytes free, but the command needs {needed} bytes plus {reserve} bytes of reserve. Try again after the thermostats have collected the waiting commands.",
	"err.send_not_queued": "The radio stick did not take the {count} commands, because its buffer overflowed. Try again in a few minutes.",
	"err.send_blocked": "The command was not sent, because the radio stick does not allow it. This is a bug of the integration, so please report it.",
	"err.send_cul_error": "The radio stick did not answer the command, and its state is {state}. Check that it is connected and try again."
}, ot = {
	"card.title": "Wochenprogramm",
	"card.stateUnknown": "Das Thermostat {entity} wurde nicht gefunden.",
	"card.loading": "Das Wochenprogramm wird geladen …",
	"temp.day": "Tag",
	"temp.night": "Nacht",
	"temp.unknown": "unbekannt",
	"reach.ok": "Thermostat erreichbar",
	"reach.silent": "Thermostat meldet sich nicht",
	"reach.link": "Funkstick getrennt",
	"reach.queueHint": "Änderungen warten in der Warteschlange und werden gesendet, sobald das Thermostat antwortet.",
	"reach.linkHint": "Änderungen warten in der Warteschlange und werden gesendet, sobald der Funkstick wieder da ist.",
	"status.unknown": "Nicht gelesen",
	"status.saved": "Gespeichert",
	"status.queued": "Wartet",
	"status.sending": "Wird gesendet",
	"status.unconfirmed": "Nicht bestätigt",
	"status.error": "Fehler",
	"status.edited": "Geändert",
	"action.save": "Speichern",
	"action.saveCount": "Speichern ({count})",
	"action.discard": "Verwerfen",
	"action.read": "Jetzt abrufen",
	"action.readWeek": "Woche abrufen",
	"action.readDay": "Diesen Tag abrufen",
	"action.resend": "Erneut senden",
	"action.editEmpty": "Leeres Programm bearbeiten",
	"action.copy": "Auf andere Tage kopieren …",
	"action.clear": "Tag leeren",
	"action.reset": "Tag zurücksetzen",
	"action.add": "Heizphase hinzufügen",
	"action.remove": "Entfernen",
	"action.merge": "Aneinandergrenzende Phasen verbinden",
	"action.back": "Zurück zur Woche",
	"action.cancel": "Abbrechen",
	"action.copyApply": "Kopieren",
	"action.overwrite": "Überschreiben",
	"action.retry": "Erneut versuchen",
	"action.dismiss": "Schließen",
	"preset.weekdays": "Werktage",
	"preset.weekend": "Wochenende",
	"preset.all": "Alle Tage",
	"empty.title": "Das Wochenprogramm wurde noch nicht gelesen.",
	"empty.body": "Das Thermostat sendet es in 28 Funktelegrammen, der Abruf der ganzen Woche dauert deshalb etwa 35 Minuten.",
	"empty.requested": "Der Abruf wurde angefordert. Die Tage erscheinen hier, sobald das Thermostat sie meldet.",
	"load.error": "Das Wochenprogramm konnte nicht geladen werden: {message}",
	"list.noHeating": "Den ganzen Tag Nachttemperatur",
	"list.unknown": "Noch nicht gelesen",
	"legend.heating": "Heizphase (Tagestemperatur)",
	"legend.night": "Nachttemperatur",
	"legend.unknown": "Nicht gelesen",
	"legend.pending": "Unterwegs",
	"footer.clean": "Keine Änderungen.",
	"footer.changed": "{count, plural, one {# Tag geändert} other {# Tage geändert}}",
	"footer.hint": "Jeder Tag braucht etwa 2 Minuten bis zum Thermostat.",
	"day.unknownHint": "Dieser Tag wurde noch nie gelesen. Speichern ersetzt den ganzen Tag im Thermostat.",
	"day.pendingHint": "Dieser Tag ist auf dem Weg zum Thermostat.",
	"day.editor": "{day} bearbeiten",
	"field.start": "Beginn",
	"field.end": "Ende",
	"field.period": "Phase {n}",
	"field.earlier": "10 Minuten früher",
	"field.later": "10 Minuten später",
	"aria.start": "{day}, Phase {n}, Beginn",
	"aria.end": "{day}, Phase {n}, Ende",
	"aria.move": "{day}, Phase {n}, verschieben",
	"aria.track": "{day}, Heizphasen",
	"aria.row": "{day}: {summary}, {status}",
	"aria.startField": "{day}, Phase {n}, Beginn als Uhrzeit",
	"aria.endField": "{day}, Phase {n}, Ende als Uhrzeit",
	"aria.startEarlier": "{day}, Phase {n}, Beginn 10 Minuten früher",
	"aria.startLater": "{day}, Phase {n}, Beginn 10 Minuten später",
	"aria.endEarlier": "{day}, Phase {n}, Ende 10 Minuten früher",
	"aria.endLater": "{day}, Phase {n}, Ende 10 Minuten später",
	"aria.remove": "{day}, Phase {n} entfernen",
	"announce.sent": "An das Thermostat gesendet: {days}.",
	"announce.unchanged": "Schon aktuell: {days}.",
	"announce.read": "Der Abruf wurde angefordert.",
	"announce.discarded": "Änderungen verworfen.",
	"announce.copied": "Kopiert nach {days}.",
	"copy.title": "{day} auf andere Tage kopieren",
	"copy.body": "Die Kopien sind Änderungen, die du noch speichern musst.",
	"confirm.title": "Tage überschreiben, die nie gelesen wurden?",
	"confirm.body": "Die Tage {days} wurden nie vom Thermostat gelesen. Speichern ersetzt sie vollständig.",
	"error.save": "Speichern fehlgeschlagen: {message}",
	"error.read": "Abruf fehlgeschlagen: {message}",
	"error.unauthorized": "Du darfst dieses Thermostat nicht ändern.",
	"error.unsupported": "Die Integration kennt die Befehle des Wochenprogramms nicht. Aktualisiere die Integration und lade die Seite neu.",
	"error.unknown": "Etwas ist schiefgelaufen.",
	"error.invalid": "Die Daten von Home Assistant haben eine unerwartete Form.",
	"err.schedule_time_invalid": "{day}: {value} ist keine Uhrzeit. Schreibe sie als HH:MM, zum Beispiel 06:30, und nimm 24:00 für das Tagesende.",
	"err.schedule_time_step": "{day}: {value} ist kein Vielfaches von {step} Minuten. Das Thermostat schaltet in Schritten von {step} Minuten.",
	"err.schedule_too_many_ranges": "{day}: {count} Zeitbereiche sind zu viele. Das Thermostat nimmt höchstens {max_ranges} Bereiche pro Tag.",
	"err.schedule_range_backwards": "{day}: Der Bereich von {start} bis {end} muss nach seinem Beginn enden. Nimm 24:00 für Mitternacht am Tagesende.",
	"err.schedule_ranges_overlap": "{day}: Die Bereiche von {first_start} bis {first_end} und von {second_start} bis {second_end} überlappen sich.",
	"err.schedule_partly_sent": "Nur ein Teil des Wochenprogramms wurde gesendet. Die Tage {sent} sind unterwegs, die Tage {unsent} wurden nicht gesendet. Setze diese Tage noch einmal.",
	"err.schedule_entity_unknown": "{entity_id} ist nicht die Klima-Entität eines Thermostats dieser Integration.",
	"err.send_unknown_device": "Das Thermostat {code} wurde noch nicht gehört, deshalb kann ihm nichts gesendet werden. Warte, bis es sendet, das kann einige Minuten dauern.",
	"err.send_device_silent": "Das Thermostat {code} ist seit {minutes} Minuten still und würde den Befehl nie abholen. Prüfe seine Batterien und den Abstand zum Funkstick.",
	"err.send_device_unconfirmed": "Das Thermostat {code} hat nie einen Befehl dieses Funksticks bestätigt, deshalb wird ihm nichts von selbst gesendet.",
	"err.send_device_unresponsive": "Das Thermostat {code} hat die letzten Nachrichten nicht bestätigt, deshalb bekommt es nur noch Befehle, die du anforderst.",
	"err.send_not_connected": "Der Funkstick ist nicht verbunden, sein Zustand ist {state}. Er verbindet sich von selbst wieder.",
	"err.send_no_credit": "Das 1-%-Sendebudget ist aufgebraucht. Es hat noch {credit} ms und braucht {minimum} ms. Versuche es in einigen Minuten noch einmal.",
	"err.send_credit_exhausted": "Das 1-%-Sendebudget blieb {minutes} Minuten unter {minimum} ms, deshalb wurde der Befehl nicht gesendet. Versuche es in einigen Minuten noch einmal.",
	"err.send_buffer_full": "Der Puffer des Funksticks hat {free} Byte frei, aber der Befehl braucht {needed} Byte plus {reserve} Byte Reserve. Versuche es noch einmal, wenn die Thermostate die wartenden Befehle abgeholt haben.",
	"err.send_not_queued": "Der Funkstick hat die {count} Befehle nicht angenommen, weil sein Puffer übergelaufen ist. Versuche es in einigen Minuten noch einmal.",
	"err.send_blocked": "Der Befehl wurde nicht gesendet, weil der Funkstick ihn nicht erlaubt. Das ist ein Fehler der Integration, bitte melde ihn.",
	"err.send_cul_error": "Der Funkstick hat den Befehl nicht beantwortet, sein Zustand ist {state}. Prüfe, ob er verbunden ist, und versuche es noch einmal."
}, st = {
	en: {
		monday: "Monday",
		tuesday: "Tuesday",
		wednesday: "Wednesday",
		thursday: "Thursday",
		friday: "Friday",
		saturday: "Saturday",
		sunday: "Sunday"
	},
	de: {
		monday: "Montag",
		tuesday: "Dienstag",
		wednesday: "Mittwoch",
		thursday: "Donnerstag",
		friday: "Freitag",
		saturday: "Samstag",
		sunday: "Sonntag"
	}
}, ct = {
	en: {
		monday: "Mon",
		tuesday: "Tue",
		wednesday: "Wed",
		thursday: "Thu",
		friday: "Fri",
		saturday: "Sat",
		sunday: "Sun"
	},
	de: {
		monday: "Mo",
		tuesday: "Di",
		wednesday: "Mi",
		thursday: "Do",
		friday: "Fr",
		saturday: "Sa",
		sunday: "So"
	}
};
function lt(e) {
	return (e ?? "").toLowerCase().startsWith("de") ? "de" : "en";
}
var ut = {
	en: {
		name: "FHT week program",
		description: "Shows and edits the week heating program of an FHT80b thermostat (German: FHT Wochenprogramm)."
	},
	de: {
		name: "FHT Wochenprogramm",
		description: "Zeigt das Wochenheizprogramm eines FHT80b-Thermostats an und ändert es (englisch: FHT week program)."
	}
};
function dt(e) {
	return ut[e];
}
var ft = /\{(\w+), plural, one \{([^}]*)\} other \{([^}]*)\}\}/;
function X(e, t, n = {}) {
	let r = e === "de" ? ot[t] : at[t];
	return r = r.replace(ft, (e, t, r, i) => (Number(n[t]) === 1 ? r : i).replace("#", String(n[t]))), r.replace(/\{(\w+)\}/g, (e, t) => t in n ? String(n[t]) : e);
}
function pt(e, t) {
	return st[e]?.[t] ?? t;
}
function mt(e, t) {
	return ct[e]?.[t] ?? t;
}
function ht(e, t) {
	let n = st.en, r = R.find((e) => n[e] === t);
	return r === void 0 ? t : pt(e, r);
}
function gt(e) {
	return e in at;
}
function Z(e, t, n = {}) {
	let r = t?.translation_key;
	if (r && gt(`err.${r}`)) {
		let i = {
			...t?.translation_placeholders ?? {},
			...n
		};
		return typeof i.day == "string" && (i.day = ht(e, i.day)), X(e, `err.${r}`, i);
	}
	return t?.code === "unauthorized" ? X(e, "error.unauthorized") : t?.code === "unknown_command" ? X(e, "error.unsupported") : t?.message || X(e, "error.unknown");
}
//#endregion
//#region src/styles.ts
var _t = o`
  :host {
    display: block;
  }
  ha-card {
    display: block;
    overflow: hidden;
  }
  .root {
    padding: var(--ha-space-4, 16px);
    display: grid;
    gap: var(--ha-space-3, 12px);
    color: var(--primary-text-color);
    font-size: var(--ha-font-size-m, 1rem);
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
  }
  .title {
    margin: 0;
    font-size: var(--ha-card-header-font-size, 1.25rem);
    font-weight: var(--ha-font-weight-medium, 500);
    color: var(--ha-card-header-color, var(--primary-text-color));
  }
  .subtitle {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .facts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
  }
  .temp {
    font-variant-numeric: tabular-nums;
  }
  .temp-label {
    color: var(--secondary-text-color);
    margin-inline-end: 4px;
  }
  .reach {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .reach::before {
    content: "";
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--success-color);
  }
  .reach.silent::before {
    background: var(--warning-color);
  }
  .reach.link::before {
    background: var(--error-color);
  }
  .banner {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--ha-space-2, 8px);
    padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
    border-radius: var(--ha-border-radius-md, 8px);
    border: 1px solid var(--warning-color);
    border-inline-start-width: 6px;
  }
  .banner.error {
    border-color: var(--error-color);
  }
  .banner.info {
    border-color: var(--info-color, var(--primary-color));
  }
  .banner p {
    margin: 0;
  }
  button {
    font: inherit;
    color: var(--primary-text-color);
    background: transparent;
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-md, 8px);
    padding: 0 var(--ha-space-3, 12px);
    min-height: 40px;
    cursor: pointer;
  }
  button.primary {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: var(--text-primary-color, #fff);
  }
  button.danger {
    border-color: var(--error-color);
  }
  button.small {
    min-height: 32px;
    padding: 0 var(--ha-space-2, 8px);
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button:focus-visible,
  input:focus-visible {
    outline: 2px solid var(--ha-color-focus, var(--primary-text-color));
    outline-offset: 2px;
  }
  .axis-row,
  .day-row {
    display: grid;
    grid-template-columns: 3.2em minmax(0, 1fr) 17.5em;
    align-items: center;
    gap: var(--ha-space-1, 4px) var(--ha-space-2, 8px);
  }
  .grid {
    display: grid;
    gap: var(--ha-space-2, 8px);
  }
  .day-row {
    padding: 2px 0;
    border-radius: var(--ha-border-radius-md, 8px);
  }
  .day-row.selected {
    background: var(--secondary-background-color);
  }
  .day-label {
    text-align: start;
    font-weight: var(--ha-font-weight-medium, 500);
    min-height: 32px;
    padding: 0 4px;
    border: none;
    background: transparent;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ha-space-2, 8px);
    justify-content: flex-end;
  }
  .summary {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
    font-variant-numeric: tabular-nums;
  }
  .narrow .day-row {
    grid-template-columns: 2.6em minmax(0, 1fr);
    width: 100%;
    text-align: start;
    background: transparent;
    border: 1px solid var(--divider-color);
    padding: var(--ha-space-2, 8px);
    min-height: 0;
  }
  .narrow .meta {
    grid-column: 2;
    justify-content: space-between;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 8px;
    border-radius: 999px;
    border: 1px solid currentcolor;
    font-size: var(--ha-font-size-s, 0.875rem);
    white-space: nowrap;
    color: var(--secondary-text-color);
  }
  .chip-saved {
    color: var(--success-color);
  }
  .chip-queued,
  .chip-sending,
  .chip-edited {
    color: var(--primary-color);
  }
  .chip-unconfirmed {
    color: var(--warning-color);
  }
  .chip-error {
    color: var(--error-color);
  }
  .chip-text {
    color: var(--primary-text-color);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .legend span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .swatch {
    width: 18px;
    height: 10px;
    border-radius: 3px;
    border: 2px solid var(--primary-color);
    background: var(--primary-color);
  }
  .swatch.night {
    background: var(--secondary-background-color);
    border-color: var(--divider-color);
  }
  .swatch.unknown {
    background: repeating-linear-gradient(135deg, transparent 0 3px, var(--divider-color) 3px 5px);
    border-color: var(--divider-color);
  }
  .swatch.pending {
    background: repeating-linear-gradient(
      135deg,
      transparent 0 3px,
      var(--card-background-color, #fff) 3px 5px
    );
    background-color: var(--primary-color);
  }
  .editor {
    display: grid;
    gap: var(--ha-space-3, 12px);
    padding: var(--ha-space-3, 12px);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-lg, 12px);
  }
  .editor-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--ha-space-2, 8px);
    justify-content: space-between;
  }
  .editor-head h3 {
    margin: 0;
    font-size: var(--ha-font-size-l, 1.125rem);
    font-weight: var(--ha-font-weight-medium, 500);
  }
  .hint {
    margin: 0;
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .periods {
    display: grid;
    gap: var(--ha-space-3, 12px);
  }
  fieldset {
    margin: 0;
    padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-md, 8px);
    display: grid;
    gap: var(--ha-space-2, 8px);
  }
  legend {
    padding: 0 4px;
    color: var(--secondary-text-color);
  }
  .fields {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-3, 12px) var(--ha-space-4, 16px);
    align-items: flex-end;
  }
  .field {
    display: grid;
    gap: 2px;
  }
  .field-label {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 0.875rem);
  }
  .stepper {
    display: flex;
    gap: 4px;
  }
  .stepper button {
    min-width: 44px;
    padding: 0;
  }
  input[type="text"] {
    font: inherit;
    width: 5.5em;
    min-height: 40px;
    text-align: center;
    box-sizing: border-box;
    color: var(--primary-text-color);
    background: var(--card-background-color);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-md, 8px);
    font-variant-numeric: tabular-nums;
  }
  input[aria-invalid="true"] {
    border-color: var(--error-color);
  }
  .field-error {
    color: var(--error-color);
    font-size: var(--ha-font-size-s, 0.875rem);
    margin: 0;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-2, 8px);
  }
  .footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
    padding-top: var(--ha-space-3, 12px);
    border-top: 1px solid var(--divider-color);
  }
  .footer-text {
    display: grid;
    gap: 2px;
  }
  .empty {
    display: grid;
    gap: var(--ha-space-3, 12px);
    justify-items: start;
    padding: var(--ha-space-4, 16px) 0;
  }
  .empty p {
    margin: 0;
  }
  dialog {
    max-width: min(28rem, calc(100vw - 32px));
    padding: var(--ha-space-4, 16px);
    color: var(--primary-text-color);
    background: var(--card-background-color);
    border: 1px solid var(--divider-color);
    border-radius: var(--ha-border-radius-lg, 12px);
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.5);
  }
  dialog h3 {
    margin: 0 0 var(--ha-space-2, 8px);
    font-size: var(--ha-font-size-l, 1.125rem);
  }
  .checks {
    display: grid;
    gap: var(--ha-space-1, 4px);
    margin: var(--ha-space-3, 12px) 0;
  }
  .checks label {
    display: flex;
    align-items: center;
    gap: var(--ha-space-2, 8px);
    min-height: 40px;
  }
  .checks input {
    width: 20px;
    height: 20px;
  }
  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: var(--ha-space-2, 8px);
  }
  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--ha-space-2, 8px);
    margin-top: var(--ha-space-3, 12px);
  }
`;
//#endregion
//#region src/ws.ts
function vt(e, t) {
	return e === null ? null : e.map((e) => ({
		start: B(e.start, t) ?? 0,
		end: B(e.end, t) ?? 0
	}));
}
function yt(e) {
	let t = B(e.limits.day_end, 1440) ?? 1440, n = {
		stepMinutes: e.limits.step_minutes,
		maxPeriods: e.limits.max_periods,
		dayEnd: t
	}, r = {};
	for (let n of R) {
		let i = e.days[n];
		r[n] = {
			status: i.status,
			periods: vt(i.periods, t),
			requested: vt(i.requested, t),
			pendingSince: i.pending_since
		};
	}
	return {
		limits: n,
		days: r,
		readAt: e.week_program_read_at,
		dayTemperature: e.day_temperature,
		nightTemperature: e.night_temperature,
		linkUp: e.link_up,
		reachable: e.reachable
	};
}
var bt = [
	"unknown",
	"saved",
	"queued",
	"sending",
	"unconfirmed",
	"error"
], xt = 1440, St = 100;
function Q(e) {
	return typeof e == "object" && !!e && !Array.isArray(e);
}
function Ct(e, t) {
	return typeof e == "number" && Number.isInteger(e) && e >= 1 && e <= t;
}
function wt(e) {
	return e === null || typeof e == "number" && Number.isFinite(e);
}
function Tt(e) {
	return e === null || typeof e == "string";
}
function Et(e) {
	return e === null || Array.isArray(e) && e.every((e) => Q(e) && typeof e.start == "string" && typeof e.end == "string");
}
function Dt(e) {
	if (!Q(e) || !Q(e.limits) || !Q(e.days)) return !1;
	let { limits: t, days: n } = e;
	return Ct(t.step_minutes, xt) && Ct(t.max_periods, St) && typeof t.day_end == "string" && R.every((e) => {
		let t = n[e];
		return Q(t) && typeof t.status == "string" && bt.includes(t.status) && Et(t.periods) && Et(t.requested) && Tt(t.pending_since);
	}) && Tt(e.week_program_read_at) && wt(e.day_temperature) && wt(e.night_temperature) && typeof e.link_up == "boolean" && typeof e.reachable == "boolean";
}
function Ot(e) {
	return Q(e) && e.closed === !0;
}
function kt(e, t, n, r, i) {
	return e.connection.subscribeMessage((e) => {
		Ot(e) ? r() : Dt(e) ? n(yt(e)) : i();
	}, {
		type: "culfw/schedule/subscribe",
		entity_id: t
	});
}
function At(e, t, n) {
	return e.callWS({
		type: "culfw/schedule/set",
		entity_id: t,
		days: n
	});
}
function jt(e, t, n) {
	return e.callWS({
		type: "culfw/schedule/refresh",
		entity_id: t,
		...n === void 0 ? {} : { days: n }
	});
}
function Mt(e) {
	if (typeof e == "object" && e) {
		let t = e, n = {};
		return typeof t.code == "string" && (n.code = t.code), typeof t.message == "string" && (n.message = t.message), typeof t.translation_key == "string" && (n.translation_key = t.translation_key), typeof t.translation_placeholders == "object" && (n.translation_placeholders = t.translation_placeholders), n;
	}
	return { message: typeof e == "string" ? e : void 0 };
}
//#endregion
//#region src/card.ts
var Nt = 540, Pt = 1e3, Ft = {
	unknown: "?",
	saved: "✓",
	queued: "…",
	sending: "↗",
	unconfirmed: "!",
	error: "✕",
	edited: "✎"
}, It = class extends I {
	static {
		this.properties = {
			_state: { state: !0 },
			_draft: { state: !0 },
			_selected: { state: !0 },
			_narrow: { state: !0 },
			_banner: { state: !0 },
			_loadError: { state: !0 },
			_busy: { state: !0 },
			_announce: { state: !0 },
			_dialog: { state: !0 },
			_copyTo: { state: !0 },
			_fieldErrors: { state: !0 },
			_readRequested: { state: !0 },
			_editEmpty: { state: !0 },
			_config: { state: !0 }
		};
	}
	constructor() {
		super(), this._unsubscribe = null, this._subscribing = !1, this._token = 0, this.preview = !1, this._state = null, this._draft = {}, this._selected = null, this._narrow = !1, this._banner = null, this._loadError = null, this._busy = !1, this._announce = "", this._dialog = null, this._copyTo = [], this._fieldErrors = {}, this._readRequested = !1, this._editEmpty = !1, this._config = null;
	}
	static {
		this.styles = _t;
	}
	setConfig(e) {
		if (typeof e?.entity != "string" || !e.entity.startsWith("climate.")) throw Error("You need to define a climate entity of the culfw integration.");
		this._config?.entity !== e.entity && (this._stop(), this._state = null, this._draft = {}, this._selected = null, this._loadError = null), this._config = e, this._ensureSubscription();
	}
	set hass(e) {
		let t = this._hass;
		this._hass = e;
		let n = this._config?.entity;
		(t === void 0 || t.language !== e.language || n !== void 0 && t.states[n] !== e.states[n]) && this.requestUpdate(), this._ensureSubscription();
	}
	get hass() {
		return this._hass;
	}
	getCardSize() {
		return 9;
	}
	getGridOptions() {
		return {
			columns: 12,
			min_columns: 6,
			rows: "auto"
		};
	}
	static getStubConfig(e, t, n) {
		return { entity: [...t, ...n].find((t) => t.startsWith("climate.") && e.entities?.[t]?.platform === "culfw") ?? "" };
	}
	static getConfigForm() {
		return {
			schema: [{
				name: "entity",
				required: !0,
				selector: { entity: { filter: {
					domain: "climate",
					integration: "culfw"
				} } }
			}, {
				name: "name",
				selector: { entity_name: {} },
				context: { entity: "entity" }
			}],
			assertConfig: (e) => {
				for (let t of ["entity", "name"]) if (e[t] !== void 0 && typeof e[t] != "string") throw Error(`'${t}' must be a string.`);
			}
		};
	}
	connectedCallback() {
		super.connectedCallback(), this._observer = new ResizeObserver((e) => {
			let t = e[0]?.contentRect.width ?? 0;
			t > 0 && (this._narrow = t < Nt);
		}), this._observer.observe(this), this._ensureSubscription();
	}
	disconnectedCallback() {
		super.disconnectedCallback(), this._observer?.disconnect(), this._stop();
	}
	updated(e) {
		if (e.has("_dialog") && this._dialog !== null) {
			let e = this.renderRoot.querySelector("dialog");
			e !== null && !e.open && e.showModal();
		}
	}
	get _language() {
		return lt(this._hass?.language);
	}
	_t(e, t = {}) {
		return X(this._language, e, t);
	}
	_day(e) {
		return pt(this._language, e);
	}
	_stop() {
		this._token += 1, clearTimeout(this._retryTimer), this._retryTimer = void 0, this._subscribing = !1, this._unsubscribe?.(), this._unsubscribe = null;
	}
	_ensureSubscription() {
		let e = this._config?.entity, t = this._hass;
		this.isConnected && e !== void 0 && t !== void 0 && t.states[e] !== void 0 && this._unsubscribe === null && !this._subscribing && this._retryTimer === void 0 && this._loadError === null && this._subscribe(t, e);
	}
	async _subscribe(e, t) {
		let n = ++this._token;
		this._subscribing = !0;
		try {
			let r = await kt(e, t, (e) => {
				n === this._token && (this._state = e, this._loadError = null, R.some((t) => e.days[t].periods !== null) && (this._readRequested = !1));
			}, () => {
				n === this._token && (this._unsubscribe?.(), this._unsubscribe = null, this._retryTimer = setTimeout(() => {
					this._retryTimer = void 0, this._ensureSubscription();
				}, Pt));
			}, () => {
				n === this._token && (this._loadError = this._t("error.invalid"));
			});
			n === this._token ? this._unsubscribe = r : r();
		} catch (e) {
			n === this._token && (this._loadError = Z(this._language, Mt(e)));
		} finally {
			n === this._token && (this._subscribing = !1);
		}
	}
	_retry() {
		this._stop(), this._loadError = null, this._ensureSubscription();
	}
	_periodsOf(e) {
		let t = this._state;
		return this._draft[e] ?? J(t.days[e]) ?? [];
	}
	_isDirty(e) {
		return this._state !== null && Y(this._draft, this._state.days).includes(e);
	}
	_edit(e, t) {
		let n = this._state, r = J(n.days[e]), i = { ...this._draft }, a = W(t);
		r !== null && Be(a, r) ? delete i[e] : i[e] = a, this._draft = i, this._banner = null, this._clearFieldErrors(e);
	}
	_clearFieldErrors(e) {
		let t = Object.fromEntries(Object.entries(this._fieldErrors).filter(([t]) => !t.startsWith(`${e}-`)));
		this._fieldErrors = t;
	}
	_onTrackChange(e, t) {
		this._selected = e, this._edit(e, t.detail.periods);
	}
	_status(e) {
		let t = this._state;
		return this._isDirty(e) ? "edited" : t.days[e].status;
	}
	_summary(e) {
		let t = this._state.days[e];
		if (this._draft[e] === void 0 && J(t) === null) return this._t("list.unknown");
		let n = this._periodsOf(e);
		return n.length === 0 ? this._t("list.noHeating") : n.map((e) => `${V(e.start)}–${V(e.end)}`).join(" · ");
	}
	_chip(e) {
		return D`<span class="chip chip-${e}"
      ><span aria-hidden="true">${Ft[e]}</span
      ><span class="chip-text">${this._t(`status.${e}`)}</span></span
    >`;
	}
	_labeler(e) {
		return (t, n) => this._t(`aria.${t}`, {
			day: this._day(e),
			n: n + 1
		});
	}
	_validation(e, t) {
		return Z(this._language, {
			translation_key: e.key,
			translation_placeholders: e.params
		}, { day: this._day(t) });
	}
	render() {
		let e = this._hass, t = this._config;
		if (e === void 0 || t === null) return D``;
		let n = e.states[t.entity];
		return D`<ha-card>
      <div class="root ${this._narrow ? "narrow" : ""}">
        ${n === void 0 ? D`<div class="banner error" role="alert">
                ${this._t("card.stateUnknown", { entity: t.entity })}
              </div>` : this._renderBody()}
        <div class="sr-only" role="status" aria-live="polite">${this._announce}</div>
      </div>
      ${this._renderDialog()}
    </ha-card>`;
	}
	_title() {
		let e = this._hass, t = this._config, n = e.states[t.entity];
		if (n === void 0) return t.entity;
		if (e.formatEntityName !== void 0) return e.formatEntityName(n, t.name);
		let r = n.attributes.friendly_name;
		return typeof t.name == "string" && t.name ? t.name : typeof r == "string" ? r : t.entity;
	}
	_renderBody() {
		let e = this._state;
		if (this._loadError !== null) return D`${this._renderHeader(null)}
        <div class="banner error" role="alert">
          <p>${this._t("load.error", { message: this._loadError })}</p>
          <button @click=${() => this._retry()}>${this._t("action.retry")}</button>
        </div>`;
		if (e === null) return D`${this._renderHeader(null)}
        <p class="hint">${this._t("card.loading")}</p>`;
		let t = R.every((t) => J(e.days[t]) === null && this._draft[t] === void 0) && !this._editEmpty, n = this._selected !== null && !t;
		return D`
      ${this._renderHeader(e)} ${this._renderBanners(e)}
      ${t ? this._renderEmpty() : this._narrow && n ? this._renderEditor(this._selected, e) : D`${this._renderGrid(e)}
              ${n ? this._renderEditor(this._selected, e) : k}
              ${this._renderLegend()}`}
      ${t ? k : this._renderFooter(e)}
    `;
	}
	_renderHeader(e) {
		let t = new Intl.NumberFormat(this._language, {
			minimumFractionDigits: 1,
			maximumFractionDigits: 1
		}), n = (e) => e === null ? this._t("temp.unknown") : `${t.format(e)} °C`, r = e === null ? k : D`<span class="reach ${e.linkUp ? e.reachable ? "ok" : "silent" : "link"}">
            ${e.linkUp ? e.reachable ? this._t("reach.ok") : this._t("reach.silent") : this._t("reach.link")}
          </span>`;
		return D`<div class="header">
      <div>
        <h2 class="title">${this._title()}</h2>
        <div class="subtitle">${this._t("card.title")}</div>
      </div>
      ${e === null ? k : D`<div class="facts">
              <span class="temp"
                ><span class="temp-label">${this._t("temp.day")}</span
                >${n(e.dayTemperature)}</span
              >
              <span class="temp"
                ><span class="temp-label">${this._t("temp.night")}</span
                >${n(e.nightTemperature)}</span
              >
              ${r}
              <button class="small" @click=${() => void this._read()}>
                ${this._t("action.readWeek")}
              </button>
            </div>`}
    </div>`;
	}
	_renderBanners(e) {
		return D`
      ${e.linkUp ? e.reachable ? k : D`<div class="banner" role="status">
                <p>${this._t("reach.silent")}. ${this._t("reach.queueHint")}</p>
              </div>` : D`<div class="banner" role="status">
              <p>${this._t("reach.link")}. ${this._t("reach.linkHint")}</p>
            </div>`}
      ${this._banner === null ? k : D`<div class="banner ${this._banner.kind}" role="alert">
              <p>${this._banner.text}</p>
              <button class="small" @click=${() => this._banner = null}>
                ${this._t("action.dismiss")}
              </button>
            </div>`}
    `;
	}
	_renderEmpty() {
		return D`<div class="empty">
      <p><strong>${this._t("empty.title")}</strong></p>
      <p>${this._readRequested ? this._t("empty.requested") : this._t("empty.body")}</p>
      <div class="actions">
        <button class="primary" ?disabled=${this._busy} @click=${() => void this._read()}>
          ${this._t("action.read")}
        </button>
        <button @click=${() => this._editEmpty = !0}>${this._t("action.editEmpty")}</button>
      </div>
    </div>`;
	}
	_renderGrid(e) {
		let t = this._narrow ? 360 : 180;
		return D`<div class="grid" role="group" aria-label=${this._t("card.title")}>
      ${this._narrow ? k : D`<div class="axis-row" aria-hidden="true">
              <span></span>
              <fht-time-axis .limits=${e.limits} .step=${t}></fht-time-axis>
              <span></span>
            </div>`}
      ${R.map((n) => this._renderRow(n, e, t))}
    </div>`;
	}
	_renderRow(e, t, n) {
		let r = t.days[e], i = this._status(e), a = J(r) === null && this._draft[e] === void 0, o = r.status === "queued" || r.status === "sending", s = this._selected === e, c = D`<fht-day-track
      .periods=${this._periodsOf(e)}
      .limits=${t.limits}
      .labeler=${this._labeler(e)}
      .axisStep=${n}
      ?interactive=${!this._narrow}
      ?unknown=${a}
      ?pending=${o}
      track-label=${this._t("aria.track", { day: this._day(e) })}
      @periods-change=${(t) => this._onTrackChange(e, t)}
    ></fht-day-track>`, l = D`<span class="meta">
      <span class="summary">${this._summary(e)}</span>${this._chip(i)}
    </span>`;
		return this._narrow ? D`<button
        class="day-row"
        aria-label=${this._t("aria.row", {
			day: this._day(e),
			summary: this._summary(e),
			status: this._t(`status.${i}`)
		})}
        @click=${() => this._selected = e}
      >
        <span class="day-label" aria-hidden="true">${mt(this._language, e)}</span>
        ${c}${l}
      </button>` : D`<div class="day-row ${s ? "selected" : ""}">
      <button
        class="day-label"
        aria-pressed=${s ? "true" : "false"}
        aria-label=${this._day(e)}
        @click=${() => this._selected = s ? null : e}
      >
        ${mt(this._language, e)}
      </button>
      ${c}${l}
    </div>`;
	}
	_renderLegend() {
		return D`<div class="legend" aria-hidden="true">
      <span><i class="swatch"></i>${this._t("legend.heating")}</span>
      <span><i class="swatch night"></i>${this._t("legend.night")}</span>
      <span><i class="swatch pending"></i>${this._t("legend.pending")}</span>
      <span><i class="swatch unknown"></i>${this._t("legend.unknown")}</span>
    </div>`;
	}
	_renderEditor(e, t) {
		let n = this._periodsOf(e), r = t.days[e], i = this._status(e), a = this._isDirty(e), o = this._draft[e] !== void 0, s = J(r) === null, c = r.status === "queued" || r.status === "sending", l = Ye(n, t.limits) !== null, u = !a && (r.status === "unconfirmed" || r.status === "error") && r.periods !== null;
		return D`<section
      class="editor"
      aria-label=${this._t("day.editor", { day: this._day(e) })}
    >
      <div class="editor-head">
        <h3>${this._day(e)}</h3>
        ${this._chip(i)}
        ${this._narrow ? D`<button class="small" @click=${() => this._selected = null}>
                ${this._t("action.back")}
              </button>` : k}
      </div>
      ${this._narrow ? D`<fht-day-track
              large
              interactive
              axis
              .axisStep=${180}
              .periods=${n}
              .limits=${t.limits}
              .labeler=${this._labeler(e)}
              ?unknown=${s && !o}
              ?pending=${c}
              track-label=${this._t("aria.track", { day: this._day(e) })}
              @periods-change=${(t) => this._onTrackChange(e, t)}
            ></fht-day-track>` : k}
      ${s ? D`<p class="hint">${this._t("day.unknownHint")}</p>` : k}
      ${c ? D`<p class="hint">${this._t("day.pendingHint")}</p>` : k}
      <div class="periods">
        ${n.map((n, r) => this._renderFields(e, n, r, t))}
      </div>
      <div class="actions">
        <button ?disabled=${!l} @click=${() => this._add(e)}>
          ${this._t("action.add")}
        </button>
        ${We(n) ? D`<button @click=${() => this._edit(e, Ge(n))}>
                ${this._t("action.merge")}
              </button>` : k}
        <button ?disabled=${n.length === 0} @click=${() => this._edit(e, [])}>
          ${this._t("action.clear")}
        </button>
        <button ?disabled=${!o} @click=${() => this._reset(e)}>
          ${this._t("action.reset")}
        </button>
        <button ?disabled=${s && !o} @click=${() => this._openCopy(e)}>
          ${this._t("action.copy")}
        </button>
        ${s || r.status === "unconfirmed" ? D`<button @click=${() => void this._read([e])}>
                ${this._t("action.readDay")}
              </button>` : k}
        ${u ? D`<button @click=${() => void this._resend(e)}>
                ${this._t("action.resend")}
              </button>` : k}
      </div>
    </section>`;
	}
	_renderFields(e, t, n, r) {
		let i = n + 1, a = this._day(e), o = (o) => {
			let s = `${e}-${n}-${o}`, c = this._fieldErrors[s], l = o === "start" ? t.start : t.end, u = r.limits.stepMinutes, d = (t) => {
				let i = this._periodsOf(e);
				this._edit(e, o === "start" ? q(i, n, l + t, r.limits) : Ze(i, n, l + t, r.limits));
			};
			return D`<div class="field">
        <span class="field-label">${this._t(`field.${o}`)}</span>
        <div class="stepper">
          <button
            aria-label=${this._t(o === "start" ? "aria.startEarlier" : "aria.endEarlier", {
				day: a,
				n: i
			})}
            @click=${() => d(-u)}
          >
            −
          </button>
          <input
            type="text"
            inputmode="numeric"
            autocomplete="off"
            aria-label=${this._t(o === "start" ? "aria.startField" : "aria.endField", {
				day: a,
				n: i
			})}
            aria-invalid=${c === void 0 ? "false" : "true"}
            aria-describedby=${c === void 0 ? k : `error-${s}`}
            .value=${Ie(c?.text ?? V(l))}
            @change=${(t) => this._onField(e, n, o, t.target.value)}
          />
          <button
            aria-label=${this._t(o === "start" ? "aria.startLater" : "aria.endLater", {
				day: a,
				n: i
			})}
            @click=${() => d(u)}
          >
            +
          </button>
        </div>
        ${c === void 0 ? k : D`<p class="field-error" id="error-${s}" role="alert">${c.message}</p>`}
      </div>`;
		};
		return D`<fieldset>
      <legend>${this._t("field.period", { n: i })}</legend>
      <div class="fields">
        ${o("start")}${o("end")}
        <button
          class="danger"
          aria-label=${this._t("aria.remove", {
			day: a,
			n: i
		})}
          @click=${() => this._edit(e, Qe(this._periodsOf(e), n))}
        >
          ${this._t("action.remove")}
        </button>
      </div>
    </fieldset>`;
	}
	_onField(e, t, n, r) {
		let i = this._state, a = `${e}-${t}-${n}`, o = { ...this._fieldErrors };
		delete o[a];
		let s = B(r, i.limits.dayEnd), c = this._periodsOf(e);
		if (c[t] === void 0) return;
		let l = c.map((e, r) => r === t ? {
			...e,
			[n]: s ?? NaN
		} : { ...e }), u = s === null ? {
			key: "schedule_time_invalid",
			params: { value: r }
		} : Ue(l, i.limits);
		u === null ? (this._fieldErrors = o, this._edit(e, l)) : this._fieldErrors = {
			...o,
			[a]: {
				text: r,
				message: this._validation(u, e)
			}
		};
	}
	_add(e) {
		let t = this._state, n = Ye(this._periodsOf(e), t.limits);
		n !== null && this._edit(e, n);
	}
	_reset(e) {
		let t = { ...this._draft };
		delete t[e], this._draft = t, this._clearFieldErrors(e);
	}
	_renderFooter(e) {
		let t = Y(this._draft, e.days).length;
		return D`<div class="footer">
      <div class="footer-text">
        <span>${t === 0 ? this._t("footer.clean") : this._t("footer.changed", { count: t })}</span>
        <span class="hint">${this._t("footer.hint")}</span>
      </div>
      <div class="actions">
        <button ?disabled=${t === 0 || this._busy} @click=${() => this._discard()}>
          ${this._t("action.discard")}
        </button>
        <button class="primary" ?disabled=${t === 0 || this._busy} @click=${() => this._save()}>
          ${t === 0 ? this._t("action.save") : this._t("action.saveCount", { count: t })}
        </button>
      </div>
    </div>`;
	}
	_discard() {
		this._draft = {}, this._fieldErrors = {}, this._banner = null, this._announce = this._t("announce.discarded");
	}
	_save() {
		let e = this._state, t = Y(this._draft, e.days);
		for (let n of t) {
			let t = Ue(this._draft[n] ?? [], e.limits);
			if (t !== null) {
				this._banner = {
					kind: "error",
					text: this._validation(t, n)
				};
				return;
			}
		}
		let n = t.filter((t) => J(e.days[t]) === null);
		n.length > 0 ? this._dialog = {
			kind: "confirm",
			days: n
		} : this._commit(t);
	}
	async _commit(e) {
		await this._send(e, this._draft);
	}
	async _resend(e) {
		let t = this._state;
		await this._send([e], { [e]: J(t.days[e]) ?? [] });
	}
	async _send(e, t) {
		let n = this._hass, r = this._config.entity;
		this._busy = !0, this._banner = null;
		try {
			let i = await At(n, r, et(t, e)), a = { ...this._draft };
			for (let e of [...i.sent, ...i.unchanged]) delete a[e];
			this._draft = a;
			let o = (e) => e.map((e) => this._day(e)).join(", "), s = [];
			i.sent.length > 0 && s.push(this._t("announce.sent", { days: o(i.sent) })), i.unchanged.length > 0 && s.push(this._t("announce.unchanged", { days: o(i.unchanged) })), this._announce = s.join(" ");
		} catch (e) {
			this._banner = {
				kind: "error",
				text: this._t("error.save", { message: Z(this._language, Mt(e)) })
			};
		} finally {
			this._busy = !1;
		}
	}
	async _read(e) {
		let t = this._hass, n = this._config.entity;
		this._busy = !0, this._banner = null;
		try {
			await jt(t, n, e), this._readRequested = !0, this._announce = this._t("announce.read");
		} catch (e) {
			this._banner = {
				kind: "error",
				text: this._t("error.read", { message: Z(this._language, Mt(e)) })
			};
		} finally {
			this._busy = !1;
		}
	}
	_openCopy(e) {
		this._copyTo = $e("weekdays", e), this._dialog = {
			kind: "copy",
			source: e
		};
	}
	_closeDialog() {
		this.renderRoot.querySelector("dialog")?.close();
	}
	_applyCopy(e) {
		let t = this._periodsOf(e);
		for (let e of this._copyTo) this._edit(e, t.map((e) => ({ ...e })));
		this._announce = this._t("announce.copied", { days: this._copyTo.map((e) => this._day(e)).join(", ") }), this._closeDialog();
	}
	_renderDialog() {
		let e = this._dialog;
		return e === null ? k : e.kind === "copy" ? this._renderCopyDialog(e.source) : D`<dialog
      role="alertdialog"
      aria-labelledby="dialog-title"
      @close=${() => this._dialog = null}
    >
      <h3 id="dialog-title">${this._t("confirm.title")}</h3>
      <p>
        ${this._t("confirm.body", { days: e.days.map((e) => this._day(e)).join(", ") })}
      </p>
      <div class="dialog-actions">
        <button @click=${() => this._closeDialog()}>${this._t("action.cancel")}</button>
        <button
          class="primary"
          @click=${() => {
			this._closeDialog(), this._commit(Y(this._draft, this._state.days));
		}}
        >
          ${this._t("action.overwrite")}
        </button>
      </div>
    </dialog>`;
	}
	_renderCopyDialog(e) {
		let t = (t) => D`<button class="small" @click=${() => this._copyTo = $e(t, e)}>
        ${this._t(`preset.${t}`)}
      </button>`;
		return D`<dialog aria-labelledby="dialog-title" @close=${() => this._dialog = null}>
      <h3 id="dialog-title">${this._t("copy.title", { day: this._day(e) })}</h3>
      <p class="hint">${this._t("copy.body")}</p>
      <div class="presets">${t("weekdays")}${t("weekend")}${t("all")}</div>
      <div class="checks">
        ${R.filter((t) => t !== e).map((e) => D`<label>
              <input
                type="checkbox"
                .checked=${this._copyTo.includes(e)}
                @change=${(t) => {
			let n = t.target.checked;
			this._copyTo = n ? R.filter((t) => t === e || this._copyTo.includes(t)) : this._copyTo.filter((t) => t !== e);
		}}
              />
              ${this._day(e)}
            </label>`)}
      </div>
      <div class="dialog-actions">
        <button @click=${() => this._closeDialog()}>${this._t("action.cancel")}</button>
        <button
          class="primary"
          ?disabled=${this._copyTo.length === 0}
          @click=${() => this._applyCopy(e)}
        >
          ${this._t("action.copyApply")}
        </button>
      </div>
    </dialog>`;
	}
}, $ = "fht-schedule-card";
customElements.get($) || customElements.define($, It);
function Lt() {
	return lt(document.querySelector("home-assistant")?.hass?.language || document.documentElement.lang);
}
window.customCards = window.customCards ?? [], window.customCards.some((e) => e.type === $) || window.customCards.push({
	type: $,
	get name() {
		return dt(Lt()).name;
	},
	get description() {
		return dt(Lt()).description;
	},
	preview: !1,
	documentationURL: "https://github.com/SpawnY0815/ha-culfw",
	getEntitySuggestion: (e, t) => t.startsWith("climate.") && e.entities?.[t]?.platform === "culfw" ? { config: {
		type: `custom:${$}`,
		entity: t
	} } : null
});
//#endregion
