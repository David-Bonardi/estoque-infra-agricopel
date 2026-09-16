// Mantem texto para preservar zeros a esquerda. O servidor tambem valida o codigo.
document.querySelectorAll('[data-numeric-code]').forEach((input) => {
  let previous = /^[0-9]*$/.test(input.value) ? input.value : '';
  input.addEventListener('beforeinput', (event) => {
    if (event.data && /[^0-9]/.test(event.data)) event.preventDefault();
  });
  input.addEventListener('paste', (event) => {
    if (/[^0-9]/.test(event.clipboardData.getData('text'))) event.preventDefault();
  });
  input.addEventListener('input', () => {
    if (/^[0-9]*$/.test(input.value)) previous = input.value;
    else input.value = previous;
  });
});
