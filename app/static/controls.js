const controls = document.querySelector('#controls');
const sample = document.querySelector('#sample');
const statusLine = document.querySelector('#run-status');
const rerun = document.querySelector('#rerun');
const exportLink = document.querySelector('#export');
let activeRun;

sample.addEventListener('change', () => {
  const address = new URL(location.href);
  address.searchParams.set('sample', sample.value);
  location.assign(address);
});

async function archive(repeat) {
  const button = repeat ? rerun : controls.querySelector('button');
  button.disabled = true;
  statusLine.textContent = '正在核算…';
  try {
    const address = repeat ? `/api/runs/${activeRun}/rerun` : '/api/runs';
    const response = await fetch(address, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: repeat ? undefined : JSON.stringify({sample: document.body.dataset.sample}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message);
    activeRun = data.id;
    statusLine.textContent = `${data.reused ? '重跑一致' : '已归档'} · ${activeRun.slice(0, 10)}`;
    exportLink.href = `/api/runs/${activeRun}/export`;
    rerun.hidden = exportLink.hidden = false;
  } catch (error) {
    statusLine.textContent = error.message || '归档失败，请重试。';
  } finally {
    button.disabled = false;
  }
}
controls.addEventListener('submit', event => { event.preventDefault(); archive(false); });
rerun.addEventListener('click', () => archive(true));
