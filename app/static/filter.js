const outletFilter = document.querySelector('#outlet-filter');
if (outletFilter) {
  const outlets = Array.from(document.querySelectorAll('#allocation-table [data-row]'));
  outletFilter.addEventListener('input', () => {
    const query = outletFilter.value.trim();
    let matches = 0;
    for (const outlet of outlets) {
      const visible = Array.from(outlet.cells).slice(0, 2).some(cell => cell.textContent.includes(query));
      outlet.hidden = !visible;
      matches += Number(visible);
    }
    document.querySelector('#filter-empty').hidden = matches > 0;
  });
}
