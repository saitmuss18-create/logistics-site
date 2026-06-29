'use strict';

// ─── Header scroll effect ───
const header = document.getElementById('header');
window.addEventListener('scroll', () => {
  header.classList.toggle('scrolled', window.scrollY > 40);
});

// ─── Burger menu ───
const burger = document.getElementById('burger');
const nav    = document.getElementById('nav');

burger.addEventListener('click', () => {
  const open = nav.classList.toggle('open');
  const [s1, s2, s3] = burger.querySelectorAll('span');
  if (open) {
    s1.style.transform = 'translateY(7px) rotate(45deg)';
    s2.style.opacity   = '0';
    s3.style.transform = 'translateY(-7px) rotate(-45deg)';
  } else {
    [s1, s2, s3].forEach(s => { s.style.transform = ''; s.style.opacity = ''; });
  }
});

nav.querySelectorAll('.nav__link').forEach(link => {
  link.addEventListener('click', () => {
    nav.classList.remove('open');
    burger.querySelectorAll('span').forEach(s => { s.style.transform = ''; s.style.opacity = ''; });
  });
});

// ─── ETA date for ship card ───
function etaDate(daysAhead) {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}
const etaEl = document.getElementById('eta-date');
if (etaEl) etaEl.textContent = etaDate(18);

// ─── Calculator ───
const USD_TO_RUB = 92;

const SHIPPING_COST = {
  vlad:  1_350,
  novo:  1_650,
  kotka: 1_800,
  kz:    1_950,
};

function fmt(n) {
  return new Intl.NumberFormat('ru-RU').format(Math.round(n));
}

function calcCustomsDuty(priceUSD, engineL, year, fuel) {
  const age = new Date().getFullYear() - year;
  const cc  = engineL * 1000;
  let duty  = 0;

  if (age <= 3) {
    const pct = 0.48;
    const minPerCC = cc <= 1000 ? 2.5 : cc <= 1500 ? 3.5 : cc <= 1800 ? 5.0 : cc <= 2300 ? 7.5 : cc <= 3000 ? 15.0 : 20.0;
    duty = Math.max(priceUSD * pct, cc * minPerCC) * USD_TO_RUB;
  } else if (age <= 5) {
    const rate = cc <= 1000 ? 1.5 : cc <= 1500 ? 1.7 : cc <= 1800 ? 2.7 : cc <= 2300 ? 2.7 : cc <= 3000 ? 6.2 : 6.6;
    duty = cc * rate * USD_TO_RUB;
  } else {
    const rate = cc <= 1000 ? 3.0 : cc <= 1500 ? 3.2 : cc <= 1800 ? 3.5 : cc <= 2300 ? 4.8 : cc <= 3000 ? 5.0 : 5.7;
    duty = cc * rate * USD_TO_RUB;
  }

  if (fuel === 'electric') duty *= 0.15;

  return duty / USD_TO_RUB; // return in USD for consistency
}

document.getElementById('calc-btn').addEventListener('click', () => {
  const price    = parseFloat(document.getElementById('lot-price').value);
  const engine   = parseFloat(document.getElementById('engine').value);
  const year     = parseInt(document.getElementById('year').value, 10);
  const fuel     = document.getElementById('fuel').value;
  const routeKey = document.getElementById('route').value;

  if (!price  || price  <= 0)  return showToast('Укажите цену лота', 'error');
  if (!engine || engine <= 0)  return showToast('Укажите объём двигателя', 'error');
  if (!year   || year   < 1990) return showToast('Укажите корректный год', 'error');

  const buyerFee  = price * 0.10;
  const usTransport = 800;
  const shipping  = SHIPPING_COST[routeKey] ?? 1_500;
  const broker    = 350;
  const cif       = price + buyerFee + usTransport + shipping + broker;
  const customs   = calcCustomsDuty(cif, engine, year, fuel);
  const govFee    = 7_500 / USD_TO_RUB;
  const ourFee    = 650;

  const total = cif + customs + govFee + ourFee;

  const rows = document.getElementById('result-rows');
  rows.innerHTML = `
    <div class="result-row"><span class="result-row__label">Цена лота</span><span class="result-row__val">$${fmt(price)}</span></div>
    <div class="result-row"><span class="result-row__label">Сбор аукциона (~10%)</span><span class="result-row__val">$${fmt(buyerFee)}</span></div>
    <div class="result-row"><span class="result-row__label">Транспорт по США</span><span class="result-row__val">$${fmt(usTransport)}</span></div>
    <div class="result-row"><span class="result-row__label">Морской фрахт</span><span class="result-row__val">$${fmt(shipping)}</span></div>
    <div class="result-row"><span class="result-row__label">Брокер</span><span class="result-row__val">$${fmt(broker)}</span></div>
    <div class="result-row"><span class="result-row__label">Таможенная пошлина</span><span class="result-row__val">$${fmt(customs)}</span></div>
    <div class="result-row"><span class="result-row__label">Госпошлина</span><span class="result-row__val">$${fmt(govFee)}</span></div>
    <div class="result-row"><span class="result-row__label">Услуги MFR Logistics</span><span class="result-row__val">$${fmt(ourFee)}</span></div>
    <div class="result-row result-row--total">
      <span class="result-row__label">Итого под ключ</span>
      <span class="result-row__val">~$${fmt(total)}</span>
    </div>
  `;

  const hint = document.querySelector('.calc-hint');
  const icon = document.querySelector('.calc-result__icon');
  if (hint) hint.style.display = 'none';
  if (icon) icon.style.display = 'none';
  rows.classList.remove('hidden');
});

// ─── Contact form ───
document.getElementById('contact-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const name  = document.getElementById('c-name').value.trim();
  const phone = document.getElementById('c-phone').value.trim();
  if (!name || !phone) {
    showToast('Заполните имя и контакт', 'error');
    return;
  }
  showToast('Заявка отправлена! Менеджер свяжется с вами в течение 30 минут.', 'ok');
  e.target.reset();
});

// ─── Toast helper ───
function showToast(msg, type = 'ok') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className   = `toast ${type}`;
  void toast.offsetWidth;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 4000);
}

// ─── Scroll animations ───
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity   = '1';
      e.target.style.transform = 'translateY(0)';
      observer.unobserve(e.target);
    }
  });
}, { threshold: 0.10 });

document.querySelectorAll('.service-card, .why-card, .route-card, .timeline__item').forEach((el, i) => {
  el.style.opacity    = '0';
  el.style.transform  = 'translateY(28px)';
  el.style.transition = `opacity .5s ease ${i * 0.07}s, transform .5s ease ${i * 0.07}s`;
  observer.observe(el);
});
