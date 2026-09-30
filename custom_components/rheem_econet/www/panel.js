class RheemEcoNetPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = [];
    this._registryLoaded = false;
    this._registryLoading = false;
    this._error = "";
  }

  set hass(value) {
    this._hass = value;
    if (!this._registryLoaded && !this._registryLoading) {
      this._loadEntityRegistry();
    }
    this._render();
  }

  get hass() {
    return this._hass;
  }

  async _loadEntityRegistry() {
    if (!this._hass) return;
    this._registryLoading = true;
    try {
      const allEntities = await this._hass.callWS({
        type: "config/entity_registry/list",
      });
      this._entries = allEntities.filter(
        (entity) => entity.platform === "rheem_econet",
      );
      this._registryLoaded = true;
      this._error = "";
    } catch (error) {
      this._error = "Could not load Rheem entities. Refresh this page to retry.";
      console.error("Rheem EcoNet panel could not load entity registry", error);
    } finally {
      this._registryLoading = false;
      this._render();
    }
  }

  _stateFor(entity) {
    return entity && this._hass.states[entity.entity_id];
  }

  _render() {
    if (!this.shadowRoot || !this._hass) return;

    const climateEntity = this._entries.find(
      (entity) => entity.entity_id.startsWith("climate."),
    );
    const climate = this._stateFor(climateEntity);
    const sensors = this._entries
      .filter((entity) => entity.entity_id.startsWith("sensor."))
      .map((entity) => ({ entity, state: this._stateFor(entity) }))
      .sort((left, right) => {
        const leftName = left.state?.attributes.friendly_name || left.entity.entity_id;
        const rightName = right.state?.attributes.friendly_name || right.entity.entity_id;
        return leftName.localeCompare(rightName);
      });
    const isAvailable = climate && !["unavailable", "unknown"].includes(climate.state);
    const current = climate?.attributes.current_temperature;
    const target = climate?.attributes.temperature;
    const targetValue = Number.isFinite(Number(target)) ? Number(target) : 120;
    const mode = climate?.state || "unavailable";
    const statusText = !isAvailable
      ? "Waiting for heater connection"
      : mode === "heat"
        ? "Enabled"
        : "Off";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          padding: 28px clamp(16px, 4vw, 56px) 48px;
          box-sizing: border-box;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        * { box-sizing: border-box; }
        .page { max-width: 1120px; margin: 0 auto; }
        .top { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
        h1 { margin: 0; font-size: clamp(26px, 4vw, 38px); font-weight: 600; letter-spacing: -0.03em; }
        .sub { margin-top: 7px; color: var(--secondary-text-color); font-size: 15px; }
        .badge { display: inline-flex; align-items: center; gap: 8px; border-radius: 999px; padding: 9px 14px; background: ${isAvailable ? "var(--success-color, #168a63)" : "var(--warning-color, #a66a00)"}; color: white; font-size: 14px; font-weight: 600; white-space: nowrap; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: white; }
        .grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr); gap: 18px; }
        .card { border: 1px solid var(--divider-color); border-radius: 18px; background: var(--card-background-color, var(--ha-card-background, var(--primary-background-color))); box-shadow: var(--ha-card-box-shadow, 0 2px 8px #00000012); padding: 24px; }
        .hero { grid-row: span 2; min-height: 350px; display: flex; flex-direction: column; justify-content: space-between; }
        .label { color: var(--secondary-text-color); font-size: 14px; text-transform: uppercase; letter-spacing: .09em; }
        .temperature { margin: 8px 0 0; font-size: clamp(76px, 13vw, 136px); line-height: 1; font-weight: 300; letter-spacing: -.08em; }
        .temperature small { font-size: .4em; vertical-align: top; letter-spacing: 0; margin-left: 8px; }
        .target-line { margin-top: 24px; display: flex; justify-content: space-between; align-items: center; gap: 14px; }
        .target-line label { color: var(--secondary-text-color); font-size: 15px; }
        .target-value { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
        input[type=range] { width: 100%; margin: 18px 0 4px; accent-color: var(--accent-color, #0789a8); }
        .range-labels { display: flex; justify-content: space-between; color: var(--secondary-text-color); font-size: 12px; }
        .actions { display: flex; gap: 10px; margin-top: 24px; }
        button { border: 0; border-radius: 12px; padding: 12px 20px; color: var(--primary-text-color); background: var(--secondary-background-color); font: inherit; font-weight: 600; cursor: pointer; }
        button.primary { color: white; background: var(--accent-color, #0789a8); }
        button[aria-pressed=true] { outline: 2px solid var(--accent-color, #0789a8); outline-offset: 2px; }
        button:disabled, input:disabled { opacity: .45; cursor: not-allowed; }
        h2 { margin: 0 0 18px; font-size: 19px; font-weight: 600; }
        .sensor-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
        .sensor { min-width: 0; border-radius: 13px; background: var(--secondary-background-color); padding: 15px; }
        .sensor-name { color: var(--secondary-text-color); font-size: 13px; line-height: 1.35; }
        .sensor-value { overflow-wrap: anywhere; margin-top: 7px; font-size: 21px; font-weight: 600; font-variant-numeric: tabular-nums; }
        .sensor-value small { color: var(--secondary-text-color); font-size: 12px; font-weight: 400; }
        .notice { margin-top: 18px; padding: 14px 16px; border-radius: 12px; background: var(--secondary-background-color); color: var(--secondary-text-color); font-size: 14px; line-height: 1.5; }
        .error { color: var(--error-color, #b3261e); margin: 10px 0; }
        .empty { padding: 38px 24px; text-align: center; color: var(--secondary-text-color); }
        @media (max-width: 760px) {
          :host { padding: 20px 14px 32px; }
          .top { align-items: flex-start; flex-direction: column; }
          .grid { grid-template-columns: 1fr; }
          .hero { grid-row: auto; min-height: 320px; }
          .sensor-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
      </style>
      <main class="page">
        <header class="top">
          <div>
            <h1>Rheem Water Heater</h1>
            <div class="sub">Prestige tankless · RTGH-RH11DVLN</div>
          </div>
          <div class="badge"><span class="dot"></span><span>${statusText}</span></div>
        </header>
        ${this._error ? `<div class="error">${this._error}</div>` : ""}
        ${climateEntity ? `
          <section class="grid">
            <article class="card hero">
              <div>
                <div class="label">Outlet water temperature</div>
                <div class="temperature"><span id="current">—</span><small>°F</small></div>
                <div class="target-line">
                  <label for="target">Target temperature</label>
                  <span class="target-value"><span id="target-readout">${targetValue}</span> °F</span>
                </div>
                <input id="target" type="range" min="110" max="140" step="1" value="${targetValue}" ${isAvailable ? "" : "disabled"} aria-label="Target water temperature" />
                <div class="range-labels"><span>110 °F</span><span>140 °F</span></div>
              </div>
              <div class="actions">
                <button id="heat" class="primary" aria-pressed="${mode === "heat"}" ${isAvailable ? "" : "disabled"}>Heat enabled</button>
                <button id="off" aria-pressed="${mode === "off"}" ${isAvailable ? "" : "disabled"}>Off</button>
              </div>
            </article>
            <article class="card">
              <h2>Live readings</h2>
              <div class="sensor-grid" id="sensors"></div>
            </article>
            <article class="card">
              <h2>Connection</h2>
              <div>${isAvailable ? "The heater is responding over the local serial connection." : "Connect the USB-to-RS-485 adapter to HAOS and the heater bus. This page will update when the heater responds."}</div>
              <div class="notice">Recirculation pump control is not exposed over a verified EcoNet command. The Rheem manual lists a separate optional push-button input; confirm the exact board wiring before connecting an isolated contact interface.</div>
            </article>
          </section>
        ` : `
          <section class="card empty">
            ${this._registryLoading ? "Loading Rheem entities…" : "No Rheem climate entity was found. Add Rheem EcoNet Tankless under Settings → Devices & services."}
          </section>
        `}
      </main>
    `;

    const currentNode = this.shadowRoot.querySelector("#current");
    if (currentNode) {
      currentNode.textContent = Number.isFinite(Number(current)) ? Number(current).toFixed(1) : "—";
    }
    const sensorContainer = this.shadowRoot.querySelector("#sensors");
    if (sensorContainer) {
      for (const { entity, state } of sensors) {
        const name = state?.attributes.friendly_name || entity.entity_id;
        const value = state && !["unavailable", "unknown"].includes(state.state)
          ? state.state
          : "—";
        const unit = state?.attributes.unit_of_measurement || "";
        const tile = document.createElement("div");
        tile.className = "sensor";
        const label = document.createElement("div");
        label.className = "sensor-name";
        label.textContent = name;
        const reading = document.createElement("div");
        reading.className = "sensor-value";
        reading.textContent = value;
        if (unit) {
          const unitNode = document.createElement("small");
          unitNode.textContent = ` ${unit}`;
          reading.append(unitNode);
        }
        tile.append(label, reading);
        sensorContainer.append(tile);
      }
    }

    const targetControl = this.shadowRoot.querySelector("#target");
    targetControl?.addEventListener("input", (event) => {
      this.shadowRoot.querySelector("#target-readout").textContent = event.target.value;
    });
    targetControl?.addEventListener("change", (event) => {
      this._setTemperature(climateEntity.entity_id, Number(event.target.value));
    });
    this.shadowRoot.querySelector("#heat")?.addEventListener("click", () => {
      this._setMode(climateEntity.entity_id, "heat");
    });
    this.shadowRoot.querySelector("#off")?.addEventListener("click", () => {
      this._setMode(climateEntity.entity_id, "off");
    });
  }

  async _setTemperature(entityId, temperature) {
    try {
      await this._hass.callService("climate", "set_temperature", {
        entity_id: entityId,
        temperature,
      });
    } catch (error) {
      this._error = "Could not send the setpoint. Check the heater connection and Home Assistant log.";
      console.error("Rheem EcoNet setpoint command failed", error);
      this._render();
    }
  }

  async _setMode(entityId, hvacMode) {
    try {
      await this._hass.callService("climate", "set_hvac_mode", {
        entity_id: entityId,
        hvac_mode: hvacMode,
      });
    } catch (error) {
      this._error = "Could not change heater mode. Check the heater connection and Home Assistant log.";
      console.error("Rheem EcoNet mode command failed", error);
      this._render();
    }
  }
}

customElements.define("rheem-econet-panel", RheemEcoNetPanel);
