// Clean Reader content script. Injected on demand; guarded so repeat injections are no-ops.
//
// Principle: this tool only reorganises what the page already shows you.
// It reads visible content only, and it stands down when a subscription or
// login prompt is on screen. It never unlocks scrolling, un-hides text,
// or touches cookies, storage or network requests.

(() => {
  if (window.__cleanReader) return;

  const DEFAULTS = { theme: 'sepia', fontSize: 19, font: 'serif', lineHeight: 1.8, width: 700 };
  const HOST_ID = 'clean-reader-host';
  const PRINT_STYLE_ID = 'clean-reader-print';

  // ---------- visibility & classification ----------

  function isVisible(el) {
    if (!(el instanceof Element)) return true;
    if (typeof el.checkVisibility === 'function') {
      return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    }
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
  }

  const NOISE_RE =
    /(^|[-_\s])(ad|ads|advert|advertisement|banner|sponsor(ed)?|promo|share|sharing|social|related|recommend(ed|ations)?|newsletter|popup|modal|cookie|consent|gdpr|outbrain|taboola|footer|sidebar|nav|navbar|menu|breadcrumbs?|comments?|byline-share|toolbar)([-_\s]|$)/i;

  const GATE_ATTR_RE = /paywall|regwall|tp-modal|tp-backdrop|piano|subscri|meter-?wall|offer-?wall|login-?wall/i;
  const GATE_TEXT_RE =
    /subscribe|subscription|subscriber|sign in to (continue|read)|log in to (continue|read)|create a free account|訂閱|付費|會員專屬|登入.*(閱讀|繼續)|免費額度|已達.*上限/i;

  const NEWSLETTER_RE = /newsletter|電子報|e-?mail updates|mailing list/i;

  function attrString(el) {
    return `${el.id || ''} ${typeof el.className === 'string' ? el.className : el.getAttribute('class') || ''}`;
  }

  function isNoise(el) {
    const role = el.getAttribute('role');
    if (role && /^(navigation|complementary|banner|contentinfo|dialog|alertdialog|search)$/.test(role)) return true;
    if (el.getAttribute('aria-hidden') === 'true') return true;
    return NOISE_RE.test(attrString(el));
  }

  function isFloating(el) {
    const p = getComputedStyle(el).position;
    return p === 'fixed' || p === 'sticky';
  }

  // A visible subscription / login prompt means the reader has no full access.
  // Clean Reader then leaves the page exactly as it is.
  function looksLikeGate(el) {
    if (!isVisible(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const attrs = attrString(el) + ' ' + (el.getAttribute('data-testid') || '');
    if (GATE_ATTR_RE.test(attrs)) return true;
    const dialogish =
      el.getAttribute('role') === 'dialog' || el.getAttribute('aria-modal') === 'true' || isFloating(el);
    if (!dialogish) return false;
    const text = (el.innerText || '').slice(0, 2000);
    // "Subscribe to our newsletter" is an annoyance, not an access gate.
    if (NEWSLETTER_RE.test(attrs + ' ' + text) && !/paywall|regwall|premium|付費|會員專屬/i.test(attrs + ' ' + text)) return false;
    return GATE_TEXT_RE.test(text);
  }

  function detectGate() {
    const candidates = document.querySelectorAll(
      '[class*="paywall" i],[id*="paywall" i],[class*="regwall" i],[class*="tp-modal" i],[class*="tp-backdrop" i],' +
        '[class*="piano" i],[id*="piano" i],[class*="subscri" i],[id*="subscri" i],[data-testid*="paywall" i],' +
        '[role="dialog"],[aria-modal="true"],dialog[open]'
    );
    for (const el of candidates) if (looksLikeGate(el)) return true;
    return false;
  }

  // ---------- extraction ----------

  const textLen = (el) => (el.innerText || el.textContent || '').trim().length;

  function linkDensity(el) {
    const total = textLen(el);
    if (!total) return 0;
    let linked = 0;
    for (const a of el.querySelectorAll('a')) linked += textLen(a);
    return linked / total;
  }

  function findContentRoot() {
    const explicit = [...document.querySelectorAll('[itemprop="articleBody"], .article-body, .post-content, .entry-content')]
      .filter(isVisible)
      .sort((a, b) => textLen(b) - textLen(a))[0];
    if (explicit && textLen(explicit) > 400) return explicit;

    const article = [...document.querySelectorAll('article')]
      .filter(isVisible)
      .sort((a, b) => textLen(b) - textLen(a))[0];
    if (article && textLen(article) > 400) return article;

    // Score ancestors of paragraph-like nodes, discounting link-heavy blocks.
    const scores = new Map();
    for (const p of document.querySelectorAll('p, pre, blockquote')) {
      if (!isVisible(p)) continue;
      const len = textLen(p);
      if (len < 25) continue;
      const add = 1 + Math.min(len / 100, 3);
      let node = p.parentElement;
      let factor = 1;
      for (let depth = 0; node && depth < 3; depth++, node = node.parentElement, factor /= 2) {
        scores.set(node, (scores.get(node) || 0) + add * factor);
      }
    }
    let best = null;
    let bestScore = 0;
    for (const [node, score] of scores) {
      const adjusted = score * (1 - linkDensity(node));
      if (adjusted > bestScore) {
        best = node;
        bestScore = adjusted;
      }
    }
    return best || document.querySelector('main') || document.body;
  }

  const KEEP = new Set([
    'P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'UL', 'OL', 'LI', 'FIGURE', 'FIGCAPTION', 'PRE', 'CODE',
    'A', 'EM', 'STRONG', 'B', 'I', 'U', 'S', 'SUB', 'SUP', 'BR', 'HR', 'TABLE', 'THEAD', 'TBODY', 'TFOOT', 'TR',
    'TH', 'TD', 'CAPTION', 'DL', 'DT', 'DD', 'MARK', 'SMALL', 'CITE', 'Q', 'TIME', 'ABBR',
  ]);
  const DROP = new Set([
    'SCRIPT', 'STYLE', 'NOSCRIPT', 'IFRAME', 'FORM', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'SVG', 'CANVAS',
    'VIDEO', 'AUDIO', 'OBJECT', 'EMBED', 'NAV', 'ASIDE', 'FOOTER', 'HEADER', 'DIALOG', 'TEMPLATE', 'LINK', 'META',
  ]);
  const BLOCK = new Set([...KEEP].filter((t) => !/^(A|EM|STRONG|B|I|U|S|SUB|SUP|BR|MARK|SMALL|CITE|Q|TIME|ABBR|CODE)$/.test(t)));
  BLOCK.add('DIV').add('SECTION').add('ARTICLE').add('MAIN');

  function absUrl(url) {
    try {
      const u = new URL(url, location.href);
      return /^https?:$/.test(u.protocol) ? u.href : null;
    } catch {
      return null;
    }
  }

  function bestFromSrcset(srcset) {
    if (!srcset) return null;
    let best = null;
    let bestW = -1;
    for (const part of srcset.split(',')) {
      const [url, size] = part.trim().split(/\s+/);
      const w = parseFloat(size) || 1;
      if (url && w > bestW) {
        best = url;
        bestW = w;
      }
    }
    return best;
  }

  function makeImg(img) {
    const w = img.naturalWidth || parseInt(img.getAttribute('width'), 10) || 0;
    if (w && w < 80) return null; // icons, trackers, avatars
    const src =
      img.currentSrc ||
      bestFromSrcset(img.getAttribute('srcset') || img.getAttribute('data-srcset')) ||
      img.getAttribute('data-src') ||
      img.getAttribute('data-lazy-src') ||
      img.getAttribute('data-original') ||
      img.getAttribute('src');
    const url = src && absUrl(src);
    if (!url) return null;
    const out = document.createElement('img');
    out.src = url;
    out.alt = img.alt || '';
    out.loading = 'lazy';
    return out;
  }

  function build(source, out) {
    for (const child of source.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        out.appendChild(document.createTextNode(child.textContent));
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      const tag = child.tagName;
      if (DROP.has(tag)) continue;
      if (tag !== 'BR' && !isVisible(child)) continue;
      if (isNoise(child)) continue;
      if (looksLikeGate(child)) continue;

      if (tag === 'IMG') {
        const img = makeImg(child);
        if (img) out.appendChild(img);
        continue;
      }
      if (tag === 'PICTURE') {
        const inner = child.querySelector('img');
        const img = inner && makeImg(inner);
        if (img) out.appendChild(img);
        continue;
      }

      if (KEEP.has(tag)) {
        if ((tag === 'UL' || tag === 'OL' || tag === 'DIV') && textLen(child) < 300 && linkDensity(child) > 0.6) continue;
        const el = document.createElement(tag === 'H1' ? 'h2' : tag.toLowerCase());
        if (tag === 'A') {
          const href = absUrl(child.getAttribute('href') || '');
          if (href) {
            el.href = href;
            el.target = '_blank';
            el.rel = 'noopener noreferrer';
          }
        }
        if (tag === 'OL' && child.getAttribute('start')) el.setAttribute('start', child.getAttribute('start'));
        if ((tag === 'TD' || tag === 'TH') && child.getAttribute('colspan')) el.setAttribute('colspan', child.getAttribute('colspan'));
        build(child, el);
        const meaningful = el.textContent.trim() || el.querySelector('img') || tag === 'BR' || tag === 'HR';
        if (meaningful) out.appendChild(el);
        continue;
      }

      // Unwrap layout containers; give text-only blocks a paragraph of their own.
      const hasBlockChild = [...child.children].some((c) => BLOCK.has(c.tagName));
      if (BLOCK.has(tag) && !hasBlockChild && textLen(child) > 0) {
        if (textLen(child) < 300 && linkDensity(child) > 0.6) continue;
        const p = document.createElement('p');
        build(child, p);
        if (p.textContent.trim() || p.querySelector('img')) out.appendChild(p);
      } else {
        build(child, out);
      }
    }
  }

  const meta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';

  function extract() {
    const root = findContentRoot();
    const content = document.createElement('div');
    build(root, content);

    const h1 = [...document.querySelectorAll('h1')].find(isVisible);
    const title = meta('meta[property="og:title"]') || h1?.innerText.trim() || document.title;
    const first = content.querySelector('h2');
    if (first && first.textContent.trim() === title.trim()) first.remove();

    const byline =
      meta('meta[name="author"]') ||
      document.querySelector('[rel="author"], [itemprop="author"], .byline, .author')?.innerText.trim().split('\n')[0] ||
      '';
    const published =
      meta('meta[property="article:published_time"]') ||
      document.querySelector('time[datetime]')?.getAttribute('datetime') ||
      '';
    const site = meta('meta[property="og:site_name"]') || location.hostname.replace(/^www\./, '');

    const text = content.textContent;
    const cjk = (text.match(/[㐀-鿿豈-﫿]/g) || []).length;
    const words = (text.replace(/[㐀-鿿豈-﫿]/g, ' ').match(/\S+/g) || []).length;
    const minutes = Math.max(1, Math.round(cjk / 400 + words / 230));

    return { title, byline, published, site, url: location.href, minutes, content };
  }

  // ---------- markdown ----------

  function inlineMd(node) {
    let out = '';
    for (const c of node.childNodes) {
      if (c.nodeType === Node.TEXT_NODE) {
        out += c.textContent.replace(/\s+/g, ' ');
        continue;
      }
      if (c.nodeType !== Node.ELEMENT_NODE) continue;
      const inner = () => inlineMd(c).trim();
      switch (c.tagName) {
        case 'STRONG':
        case 'B':
          out += inner() ? `**${inner()}**` : '';
          break;
        case 'EM':
        case 'I':
        case 'CITE':
          out += inner() ? `*${inner()}*` : '';
          break;
        case 'CODE':
          out += `\`${c.textContent}\``;
          break;
        case 'A':
          out += c.getAttribute('href') ? `[${inner()}](${c.getAttribute('href')})` : inner();
          break;
        case 'IMG':
          out += `![${c.alt}](${c.src})`;
          break;
        case 'BR':
          out += '  \n';
          break;
        default:
          out += inlineMd(c);
      }
    }
    return out;
  }

  function blockMd(node, depth = 0) {
    let out = '';
    for (const c of node.childNodes) {
      if (c.nodeType === Node.TEXT_NODE) {
        if (c.textContent.trim()) out += c.textContent.trim() + '\n\n';
        continue;
      }
      if (c.nodeType !== Node.ELEMENT_NODE) continue;
      const tag = c.tagName;
      if (/^H[1-6]$/.test(tag)) out += `${'#'.repeat(Number(tag[1]))} ${inlineMd(c).trim()}\n\n`;
      else if (tag === 'P') out += inlineMd(c).trim() + '\n\n';
      else if (tag === 'BLOCKQUOTE')
        out += blockMd(c).trim().split('\n').map((l) => `> ${l}`).join('\n') + '\n\n';
      else if (tag === 'UL' || tag === 'OL') {
        let i = Number(c.getAttribute('start')) || 1;
        for (const li of c.children) {
          if (li.tagName !== 'LI') continue;
          const marker = tag === 'OL' ? `${i++}.` : '-';
          const nested = [...li.children].filter((x) => x.tagName === 'UL' || x.tagName === 'OL');
          const clone = li.cloneNode(true);
          clone.querySelectorAll(':scope > ul, :scope > ol').forEach((x) => x.remove());
          out += `${'  '.repeat(depth)}${marker} ${inlineMd(clone).trim()}\n`;
          for (const n of nested) out += blockMd({ childNodes: [n] }, depth + 1);
        }
        if (depth === 0) out += '\n';
      } else if (tag === 'PRE') out += '```\n' + c.textContent.replace(/\n$/, '') + '\n```\n\n';
      else if (tag === 'HR') out += '---\n\n';
      else if (tag === 'IMG') out += `![${c.alt}](${c.src})\n\n`;
      else if (tag === 'FIGURE') {
        for (const img of c.querySelectorAll('img')) out += `![${img.alt}](${img.src})\n`;
        const cap = c.querySelector('figcaption');
        out += cap ? `*${inlineMd(cap).trim()}*\n\n` : '\n';
      } else if (tag === 'TABLE') {
        const rows = [...c.querySelectorAll('tr')].map((tr) =>
          [...tr.children].map((td) => inlineMd(td).trim().replace(/\|/g, '\\|'))
        );
        if (rows.length) {
          const cols = Math.max(...rows.map((r) => r.length));
          const pad = (r) => [...r, ...Array(cols - r.length).fill('')];
          out += `| ${pad(rows[0]).join(' | ')} |\n| ${Array(cols).fill('---').join(' | ')} |\n`;
          for (const r of rows.slice(1)) out += `| ${pad(r).join(' | ')} |\n`;
          out += '\n';
        }
      } else out += blockMd(c, depth);
    }
    return out;
  }

  function toMarkdown(article) {
    const yaml = (v) => JSON.stringify(v ?? '');
    const front = [
      '---',
      `title: ${yaml(article.title)}`,
      `source: ${yaml(article.url)}`,
      `site: ${yaml(article.site)}`,
      article.byline ? `author: ${yaml(article.byline)}` : null,
      article.published ? `published: ${yaml(article.published)}` : null,
      `saved: ${yaml(new Date().toISOString())}`,
      '---',
    ]
      .filter(Boolean)
      .join('\n');
    const body = blockMd(article.content).replace(/\n{3,}/g, '\n\n').trim();
    return `${front}\n\n# ${article.title}\n\n${body}\n`;
  }

  function fileName(title) {
    const safe = title.replace(/[\\/:*?"<>|\n\r]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);
    return `${safe || 'article'}.md`;
  }

  // ---------- settings ----------

  async function loadSettings() {
    try {
      return { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
    } catch {
      return { ...DEFAULTS };
    }
  }

  function saveSettings(patch) {
    try {
      chrome.storage.sync.set(patch);
    } catch {
      /* storage unavailable (e.g. tests) */
    }
  }

  // ---------- reader overlay ----------

  let current = null; // { host, article, settings, prevOverflow }

  const STYLE = `
    :host { all: initial; }
    .wrap {
      --bg: #f6f0e4; --fg: #2b2620; --muted: #7a6f60; --line: #e2d8c6; --accent: #9a4a1c; --bar: rgba(246,240,228,.92);
      position: fixed; inset: 0; overflow-y: auto; background: var(--bg); color: var(--fg);
      -webkit-font-smoothing: antialiased; scroll-behavior: smooth;
    }
    .wrap[data-theme="light"] { --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --line: #e5e5ea; --accent: #0a58ca; --bar: rgba(255,255,255,.92); }
    .wrap[data-theme="dark"]  { --bg: #17181a; --fg: #dcdad5; --muted: #8e8c87; --line: #2c2d30; --accent: #e0a46e; --bar: rgba(23,24,26,.92); }
    .wrap[data-font="serif"] .article { font-family: "Noto Serif TC","Source Han Serif TC","Songti TC","PMingLiU",Georgia,serif; }
    .wrap[data-font="sans"]  .article { font-family: "Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,-apple-system,sans-serif; }

    .bar {
      position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 6px; justify-content: center;
      padding: 10px 16px; background: var(--bar); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line);
      font: 13px/1 system-ui, -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif;
    }
    .bar button {
      all: unset; cursor: pointer; padding: 7px 11px; border-radius: 8px; color: var(--fg);
      border: 1px solid var(--line); background: transparent; white-space: nowrap;
    }
    .bar button:hover { border-color: var(--muted); }
    .bar button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .bar .close { margin-left: auto; }
    .bar .spacer { flex: 1 0 0; }

    .article {
      box-sizing: border-box; max-width: calc(var(--w) * 1px); margin: 0 auto; padding: 48px 20px 120px;
      font-size: calc(var(--fs) * 1px); line-height: var(--lh); overflow-wrap: anywhere;
    }
    .site { color: var(--muted); font-size: .72em; letter-spacing: .08em; text-transform: uppercase; }
    h1.title { font-size: 1.9em; line-height: 1.25; margin: .4em 0 .35em; font-weight: 700; }
    .meta { color: var(--muted); font-size: .78em; margin-bottom: 2.2em; padding-bottom: 1.2em; border-bottom: 1px solid var(--line); }
    .body h2 { font-size: 1.35em; line-height: 1.35; margin: 1.8em 0 .6em; }
    .body h3, .body h4, .body h5, .body h6 { font-size: 1.12em; margin: 1.6em 0 .5em; }
    .body p { margin: 0 0 1.15em; }
    .body a { color: var(--accent); text-underline-offset: 3px; }
    .body img { display: block; max-width: 100%; height: auto; margin: 1.6em auto .6em; border-radius: 4px; }
    .body figure { margin: 1.8em 0; }
    .body figcaption { color: var(--muted); font-size: .8em; line-height: 1.5; text-align: center; }
    .body blockquote { margin: 1.4em 0; padding: .1em 0 .1em 1.1em; border-left: 3px solid var(--accent); color: var(--muted); }
    .body pre { overflow-x: auto; padding: 1em; border-radius: 6px; background: var(--line); font-size: .8em; line-height: 1.5; }
    .body code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .88em; }
    .body ul, .body ol { padding-left: 1.4em; margin: 0 0 1.15em; }
    .body li { margin: .3em 0; }
    .body hr { border: 0; border-top: 1px solid var(--line); margin: 2em 0; }
    .body table { border-collapse: collapse; width: 100%; font-size: .85em; margin: 1.4em 0; display: block; overflow-x: auto; }
    .body th, .body td { border: 1px solid var(--line); padding: .45em .6em; text-align: left; }
    .source { margin-top: 3em; padding-top: 1.2em; border-top: 1px solid var(--line); color: var(--muted); font-size: .75em; }
    .source a { color: var(--muted); }

    .toast {
      position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 3;
      padding: 10px 16px; border-radius: 999px; background: var(--fg); color: var(--bg);
      font: 13px/1.2 system-ui, "PingFang TC", sans-serif; opacity: 0; transition: opacity .2s; pointer-events: none;
    }
    .toast.show { opacity: 1; }
    @media (prefers-reduced-motion: reduce) { .wrap { scroll-behavior: auto; } .toast { transition: none; } }
  `;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  function formatDate(iso) {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long', day: 'numeric' });
  }

  function applySettings(wrap, s) {
    wrap.dataset.theme = s.theme;
    wrap.dataset.font = s.font;
    wrap.style.setProperty('--fs', s.fontSize);
    wrap.style.setProperty('--lh', s.lineHeight);
    wrap.style.setProperty('--w', s.width);
  }

  function toast(root, msg) {
    const t = root.querySelector('.toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('show'), 1800);
  }

  function pageToast(msg) {
    const el = document.createElement('div');
    el.textContent = msg;
    el.setAttribute('role', 'status');
    el.style.cssText =
      'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:2147483647;padding:10px 16px;' +
      'border-radius:999px;background:#1d1d1f;color:#fff;font:13px/1.3 system-ui,"PingFang TC",sans-serif;' +
      'max-width:min(90vw,520px);text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.25)';
    document.documentElement.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  function download(name, text) {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.documentElement.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const GATE_MSG = '這頁顯示了訂閱或登入提示。請先用你的帳號登入，再開啟純淨閱讀。';

  async function openReader() {
    if (current) return { ok: true, open: true };
    if (detectGate()) {
      pageToast(GATE_MSG);
      return { ok: false, error: 'gated' };
    }
    const article = extract();
    if (textLen(article.content) < 200) {
      pageToast('這頁找不到足夠的文章內容。');
      return { ok: false, error: 'no-content' };
    }
    const settings = await loadSettings();

    const host = document.createElement('div');
    host.id = HOST_ID;
    host.style.cssText = 'position:fixed;inset:0;z-index:2147483647;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="wrap" role="document" tabindex="-1">
        <div class="bar" role="toolbar" aria-label="純淨閱讀工具列">
          <button data-act="smaller" aria-label="縮小字體">A−</button>
          <button data-act="larger" aria-label="放大字體">A+</button>
          <button data-act="theme">主題</button>
          <button data-act="font">字體</button>
          <button data-act="narrow" aria-label="縮窄版面">⇥⇤</button>
          <button data-act="wide" aria-label="加寬版面">⇤⇥</button>
          <button data-act="copy">複製 Markdown</button>
          <button data-act="download">下載 .md</button>
          <button data-act="print">列印</button>
          <button data-act="close" class="close" aria-label="關閉閱讀模式">關閉 Esc</button>
        </div>
        <main class="article">
          <div class="site">${esc(article.site)}</div>
          <h1 class="title">${esc(article.title)}</h1>
          <div class="meta">${[article.byline, article.published && formatDate(article.published), `約 ${article.minutes} 分鐘`]
            .filter(Boolean)
            .map(esc)
            .join(' · ')}</div>
          <div class="body"></div>
          <div class="source">原文：<a href="${esc(article.url)}" target="_blank" rel="noopener noreferrer">${esc(article.url)}</a></div>
        </main>
        <div class="toast" aria-live="polite"></div>
      </div>`;
    root.querySelector('.body').appendChild(article.content);

    const wrap = root.querySelector('.wrap');
    applySettings(wrap, settings);

    const update = (patch) => {
      Object.assign(settings, patch);
      applySettings(wrap, settings);
      saveSettings(patch);
    };
    const THEMES = ['sepia', 'light', 'dark'];
    const THEME_NAMES = { sepia: '米色', light: '白色', dark: '深色' };

    root.querySelector('.bar').addEventListener('click', async (e) => {
      const act = e.target.closest('button')?.dataset.act;
      if (!act) return;
      if (act === 'smaller') update({ fontSize: Math.max(14, settings.fontSize - 1) });
      if (act === 'larger') update({ fontSize: Math.min(30, settings.fontSize + 1) });
      if (act === 'narrow') update({ width: Math.max(520, settings.width - 60) });
      if (act === 'wide') update({ width: Math.min(1000, settings.width + 60) });
      if (act === 'theme') {
        const next = THEMES[(THEMES.indexOf(settings.theme) + 1) % THEMES.length];
        update({ theme: next });
        toast(root, `主題：${THEME_NAMES[next]}`);
      }
      if (act === 'font') {
        update({ font: settings.font === 'serif' ? 'sans' : 'serif' });
        toast(root, settings.font === 'serif' ? '字體：明體' : '字體：黑體');
      }
      if (act === 'copy') {
        try {
          await navigator.clipboard.writeText(toMarkdown(article));
          toast(root, '已複製 Markdown');
        } catch {
          toast(root, '複製失敗，請改用下載');
        }
      }
      if (act === 'download') {
        download(fileName(article.title), toMarkdown(article));
        toast(root, '已下載');
      }
      if (act === 'print') window.print();
      if (act === 'close') closeReader();
    });

    const onKey = (e) => {
      if (e.key === 'Escape') closeReader();
    };
    document.addEventListener('keydown', onKey, true);

    const printStyle = document.createElement('style');
    printStyle.id = PRINT_STYLE_ID;
    printStyle.textContent = `@media print {
      body > *:not(#${HOST_ID}) { display: none !important; }
      html, body { overflow: visible !important; height: auto !important; }
      #${HOST_ID} { position: static !important; }
    }`;
    document.head.appendChild(printStyle);

    const prevOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    document.body.appendChild(host);
    wrap.focus();

    current = { host, article, onKey, prevOverflow, printStyle };
    return { ok: true, open: true };
  }

  function closeReader() {
    if (!current) return { ok: true, open: false };
    current.host.remove();
    current.printStyle.remove();
    document.removeEventListener('keydown', current.onKey, true);
    document.documentElement.style.overflow = current.prevOverflow;
    current = null;
    return { ok: true, open: false };
  }

  // ---------- declutter (non-destructive, reversible) ----------

  const ANNOYANCES = [
    '[id*="cookie" i]', '[class*="cookie" i]', '[id*="consent" i]', '[class*="consent" i]', '[id*="gdpr" i]',
    '[class*="gdpr" i]', '#onetrust-banner-sdk', '#CybotCookiebotDialog', '.fc-consent-root',
    '[class*="newsletter" i][class*="popup" i]', '[class*="newsletter" i][class*="modal" i]', '[class*="signup-modal" i]',
    '[id^="google_ads"]', '[id^="div-gpt-ad"]', '.adsbygoogle', '[data-ad-slot]', '[data-ad-unit]', '[class*="ad-slot" i]',
    '[class*="ad-container" i]', 'iframe[src*="doubleclick"]', 'iframe[src*="googlesyndication"]',
    '[class*="taboola" i]', '[id*="taboola" i]', '[class*="outbrain" i]', '[id*="outbrain" i]',
    '[class*="sticky-video" i]', '[class*="floating-video" i]', '[class*="push-notification" i]',
    '[class*="app-banner" i]', '[class*="smart-banner" i]',
  ].join(',');

  const HIDDEN_ATTR = 'data-clean-reader-hidden';

  function hide(el) {
    if (el.hasAttribute(HIDDEN_ATTR) || el.id === HOST_ID) return false;
    el.setAttribute(HIDDEN_ATTR, el.getAttribute('style') || '');
    el.style.setProperty('display', 'none', 'important');
    return true;
  }

  function declutter() {
    if (detectGate()) {
      pageToast(GATE_MSG);
      return { ok: false, error: 'gated' };
    }
    let count = 0;
    for (const el of document.querySelectorAll(ANNOYANCES)) {
      if (el === document.body || el === document.documentElement) continue;
      if (el.closest('article, main, [itemprop="articleBody"]') && !isFloating(el)) continue;
      if (looksLikeGate(el)) continue;
      if (hide(el)) count++;
    }
    // Small floating bars (sticky ads, app banners, chat bubbles). Large overlays are left alone.
    const viewport = innerWidth * innerHeight;
    for (const el of document.body.querySelectorAll('*')) {
      if (el.id === HOST_ID || !isFloating(el) || !isVisible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width * r.height > viewport * 0.35 || r.height > innerHeight * 0.4) continue;
      if (el.closest('article, main') && getComputedStyle(el).position === 'sticky') continue;
      if (looksLikeGate(el)) continue;
      if (hide(el)) count++;
    }
    pageToast(count ? `已隱藏 ${count} 個干擾元素。重新整理頁面即可還原。` : '沒有找到需要清除的干擾元素。');
    return { ok: true, hidden: count };
  }

  function restore() {
    let count = 0;
    for (const el of document.querySelectorAll(`[${HIDDEN_ATTR}]`)) {
      const prev = el.getAttribute(HIDDEN_ATTR);
      if (prev) el.setAttribute('style', prev);
      else el.removeAttribute('style');
      el.removeAttribute(HIDDEN_ATTR);
      count++;
    }
    return { ok: true, restored: count };
  }

  // ---------- messaging ----------

  async function handle(action) {
    switch (action) {
      case 'toggle-reader':
        return current ? closeReader() : openReader();
      case 'open-reader':
        return openReader();
      case 'close-reader':
        return closeReader();
      case 'declutter':
        return declutter();
      case 'restore':
        return restore();
      case 'markdown': {
        if (!current && detectGate()) return { ok: false, error: 'gated' };
        const article = current?.article || extract();
        return { ok: true, markdown: toMarkdown(article), fileName: fileName(article.title) };
      }
      case 'status':
        return { ok: true, open: !!current };
      default:
        return { ok: false, error: `unknown action: ${action}` };
    }
  }

  window.__cleanReader = { handle, extract, toMarkdown, detectGate };

  if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      handle(msg?.action)
        .then(sendResponse)
        .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
      return true;
    });
  }
})();
