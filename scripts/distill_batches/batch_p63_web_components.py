"""Frontend — Web Components, Shadow DOM, and custom elements."""

PAIRS = [
    (
        "frontend/web-components",
        "Show Web Components patterns: custom elements, Shadow DOM, slots, lifecycle, and form-associated elements.",
        """Web Components patterns:

```javascript
// --- Basic custom element with Shadow DOM ---

class AppCard extends HTMLElement {
  static observedAttributes = ['title', 'variant'];

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue !== newValue) {
      this.render();
    }
  }

  get variant() {
    return this.getAttribute('variant') || 'default';
  }

  render() {
    const title = this.getAttribute('title') || '';
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
          transition: box-shadow 0.2s;
        }
        :host(:hover) {
          box-shadow: 0 4px 16px rgba(0,0,0,0.15);
        }
        :host([variant="highlighted"]) {
          border: 2px solid var(--primary-color, #3b82f6);
        }
        .header {
          padding: 1rem;
          background: var(--card-header-bg, #f8f9fa);
          border-bottom: 1px solid #e5e7eb;
        }
        .header h3 {
          margin: 0;
          font-size: 1.1rem;
        }
        .body {
          padding: 1rem;
        }
        .footer {
          padding: 0.75rem 1rem;
          border-top: 1px solid #e5e7eb;
          display: flex;
          justify-content: flex-end;
          gap: 0.5rem;
        }
        /* Style slotted content */
        ::slotted(img) {
          width: 100%;
          height: auto;
        }
      </style>
      <div class="header">
        <h3>${title}</h3>
        <slot name="header-extra"></slot>
      </div>
      <div class="body">
        <slot></slot>
      </div>
      <div class="footer">
        <slot name="actions"></slot>
      </div>
    `;
  }
}

customElements.define('app-card', AppCard);

// Usage:
// <app-card title="Product" variant="highlighted">
//   <img src="product.jpg" alt="Product" />
//   <p>Description here</p>
//   <button slot="actions">Buy Now</button>
// </app-card>


// --- Form-associated custom element ---

class AppInput extends HTMLElement {
  static formAssociated = true;
  static observedAttributes = ['label', 'required', 'type', 'pattern'];

  #internals;
  #input;

  constructor() {
    super();
    this.#internals = this.attachInternals();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
    this.#input = this.shadowRoot.querySelector('input');

    this.#input.addEventListener('input', () => {
      this.#internals.setFormValue(this.#input.value);
      this.#validate();
    });

    this.#input.addEventListener('blur', () => {
      this.#validate();
    });
  }

  get value() { return this.#input?.value || ''; }
  set value(v) {
    if (this.#input) this.#input.value = v;
    this.#internals.setFormValue(v);
  }

  #validate() {
    if (this.hasAttribute('required') && !this.#input.value) {
      this.#internals.setValidity(
        { valueMissing: true },
        'This field is required',
        this.#input
      );
    } else if (this.#input.validity.patternMismatch) {
      this.#internals.setValidity(
        { patternMismatch: true },
        'Invalid format',
        this.#input
      );
    } else {
      this.#internals.setValidity({});
    }
  }

  // Lifecycle
  formResetCallback() {
    this.#input.value = '';
    this.#internals.setFormValue('');
  }

  formDisabledCallback(disabled) {
    this.#input.disabled = disabled;
  }

  render() {
    const label = this.getAttribute('label') || '';
    const type = this.getAttribute('type') || 'text';
    const required = this.hasAttribute('required');

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; margin-bottom: 1rem; }
        label { display: block; margin-bottom: 0.25rem; font-weight: 500; }
        input {
          width: 100%;
          padding: 0.5rem;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          font: inherit;
          box-sizing: border-box;
        }
        input:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59,130,246,0.1);
        }
        :host(:invalid) input { border-color: #ef4444; }
      </style>
      <label for="input">${label}${required ? ' *' : ''}</label>
      <input id="input" type="${type}"
             ${required ? 'required' : ''}
             ${this.getAttribute('pattern') ? `pattern="${this.getAttribute('pattern')}"` : ''} />
    `;
  }
}

customElements.define('app-input', AppInput);

// Usage in regular <form>:
// <form>
//   <app-input label="Email" type="email" required name="email"></app-input>
//   <app-input label="Phone" pattern="\\d{3}-\\d{3}-\\d{4}" name="phone"></app-input>
//   <button type="submit">Submit</button>
// </form>


// --- Event communication pattern ---

class AppNotification extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  show(message, type = 'info', duration = 5000) {
    this.shadowRoot.innerHTML = `
      <style>
        .notification {
          padding: 1rem;
          border-radius: 8px;
          margin: 0.5rem 0;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          animation: slideIn 0.3s ease-out;
        }
        .info { background: #dbeafe; color: #1e40af; }
        .success { background: #dcfce7; color: #166534; }
        .error { background: #fee2e2; color: #991b1b; }
        .close { margin-left: auto; cursor: pointer; background: none;
                 border: none; font-size: 1.2rem; color: inherit; }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      </style>
      <div class="notification ${type}" role="alert">
        <span>${message}</span>
        <button class="close" aria-label="Dismiss">&times;</button>
      </div>
    `;

    this.shadowRoot.querySelector('.close').addEventListener('click', () => {
      this.dismiss();
    });

    if (duration > 0) {
      setTimeout(() => this.dismiss(), duration);
    }
  }

  dismiss() {
    this.dispatchEvent(new CustomEvent('dismissed', { bubbles: true }));
    this.remove();
  }
}

customElements.define('app-notification', AppNotification);
```

Web Components patterns:
1. **Shadow DOM** — encapsulated styles that don't leak to/from parent page
2. **Slots** — named and default slots for flexible content composition
3. **`:host` selector** — style the custom element itself from within shadow
4. **Form-associated** — `attachInternals()` integrates with native `<form>` validation
5. **Custom events** — `dispatchEvent(new CustomEvent(...))` for component communication"""
    ),
]
