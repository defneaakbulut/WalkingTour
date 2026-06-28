const navToggle = document.querySelector('[data-nav-toggle]');
const nav = document.querySelector('[data-nav]');

if (navToggle) {
  navToggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  nav.addEventListener('click', (event) => {
    if (event.target.closest('a')) {
      nav.classList.remove('open');
      navToggle.setAttribute('aria-expanded', 'false');
    }
  });
}

document.querySelectorAll('[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
});

const registrationForm = document.querySelector('[data-register]');

if (registrationForm) {
  const languageSection = registrationForm.querySelector('[data-languages]');
  const languageInputs = [...languageSection.querySelectorAll('[name=languages]')];

  const syncLanguageFields = () => {
    const isGuide = registrationForm.querySelector('[name=role]:checked').value === 'guide';
    const hasLanguage = languageInputs.some((input) => input.checked);

    languageSection.hidden = !isGuide;
    languageInputs[0].setCustomValidity(
      isGuide && !hasLanguage ? 'Choose at least one language.' : '',
    );
  };

  registrationForm.querySelectorAll('[name=role]').forEach((input) => {
    input.addEventListener('change', syncLanguageFields);
  });

  languageInputs.forEach((input) => {
    input.addEventListener('change', syncLanguageFields);
  });

  registrationForm.addEventListener('submit', syncLanguageFields);
  syncLanguageFields();
}

const bookingForm = document.querySelector('[data-booking-form]');

if (bookingForm) {
  const guestContainer = bookingForm.querySelector('[data-guests]');
  const addGuestButton = bookingForm.querySelector('[data-add-guest]');
  let guestCount = 0;

  addGuestButton.addEventListener('click', () => {
    if (guestCount >= 3) {
      return;
    }

    guestCount += 1;
    const label = document.createElement('label');
    label.className = 'guest-field';
    label.innerHTML = `Guest ${guestCount} — first & last name
      <input name="guest_names" required maxlength="120">
      <button class="remove-guest" type="button" aria-label="Remove guest">×</button>`;

    label.querySelector('button').addEventListener('click', () => {
      label.remove();
      guestCount -= 1;
    });

    guestContainer.append(label);

    if (guestCount >= 3) {
      addGuestButton.hidden = true;
    }
  });

  guestContainer.addEventListener('click', () => {
    if (guestCount < 3) {
      addGuestButton.hidden = false;
    }
  });
}

const lightboxDialog = document.querySelector('[data-lightbox-dialog]');

if (lightboxDialog) {
  const lightboxImage = lightboxDialog.querySelector('img');

  document.querySelectorAll('[data-lightbox]').forEach((button) => {
    button.addEventListener('click', () => {
      lightboxImage.src = button.dataset.lightbox;
      lightboxDialog.showModal();
    });
  });

  lightboxDialog.querySelector('[data-lightbox-close]').addEventListener('click', () => {
    lightboxDialog.close();
  });

  lightboxDialog.addEventListener('click', (event) => {
    if (event.target === lightboxDialog) {
      lightboxDialog.close();
    }
  });
}

window.setTimeout(() => {
  document.querySelectorAll('.flash').forEach((element) => element.remove());
}, 5000);
