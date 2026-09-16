(() => {
  const form = document.getElementById('movement-form');
  if (!form) return;
  const fields = Object.fromEntries(['kind', 'item', 'source', 'destination', 'asset', 'quantity', 'recipient', 'recipient_department'].map(name => [name, form.elements.namedItem(name)]));
  const assetOptions = Array.from(fields.asset.options, option => option.cloneNode(true));
  const hint = document.getElementById('movement-hint');

  function show(name, visible, required = visible) {
    form.querySelector(`[data-field="${name}"]`).hidden = !visible;
    fields[name].disabled = !visible;
    fields[name].required = required;
    if (!visible && name !== 'quantity') fields[name].value = '';
  }

  function update() {
    const kind = fields.kind.value;
    const tracking = fields.item.selectedOptions[0]?.dataset.tracking;
    const individual = tracking === 'individual';
    show('source', kind === 'exit' || kind === 'transfer');
    show('destination', kind === 'entry' || kind === 'transfer');
    show('recipient', kind === 'exit' || kind === 'transfer', false);
    show('recipient_department', kind === 'exit' || kind === 'transfer', false);
    show('asset', individual);
    show('quantity', tracking === 'quantity');
    if (individual) fields.quantity.value = '1';

    const previous = fields.asset.value;
    const available = assetOptions.filter(option => !option.value || (
      option.dataset.item === fields.item.value && (
        kind === 'entry' ? option.dataset.branch === '' :
        option.dataset.branch !== '' && (!fields.source.value || option.dataset.branch === fields.source.value)
      )
    ));
    fields.asset.replaceChildren(...available.map(option => option.cloneNode(true)));
    fields.asset.value = available.some(option => option.value === previous) ? previous : '';
    hint.hidden = !individual;
    hint.textContent = available.length > 1
      ? 'Cada patrimônio representa 1 equipamento. A quantidade será registrada automaticamente.'
      : 'Nenhum patrimônio disponível para este item e origem. Confira o cadastro e a localização do equipamento.';
  }
  ['kind', 'item', 'source'].forEach(name => fields[name].addEventListener('change', update));
  update();
})();
