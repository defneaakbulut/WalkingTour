const navToggle=document.querySelector('[data-nav-toggle]');
const nav=document.querySelector('[data-nav]');
if(navToggle){navToggle.addEventListener('click',()=>{const open=nav.classList.toggle('open');navToggle.setAttribute('aria-expanded',String(open))});nav.addEventListener('click',e=>{if(e.target.closest('a')){nav.classList.remove('open');navToggle.setAttribute('aria-expanded','false')}})}

document.querySelectorAll('[data-confirm]').forEach(form=>form.addEventListener('submit',e=>{if(!window.confirm(form.dataset.confirm))e.preventDefault()}));

const register=document.querySelector('[data-register]');
if(register){const languages=register.querySelector('[data-languages]');const sync=()=>{languages.hidden=register.querySelector('[name=role]:checked').value!=='guide'};register.querySelectorAll('[name=role]').forEach(input=>input.addEventListener('change',sync));sync()}

const booking=document.querySelector('[data-booking-form]');
if(booking){let guests=0;const container=booking.querySelector('[data-guests]');booking.querySelector('[data-add-guest]').addEventListener('click',()=>{if(guests>=3)return;guests+=1;const label=document.createElement('label');label.className='guest-field';label.innerHTML=`Guest ${guests} — first & last name<input name="guest_names" required maxlength="120"><button class="remove-guest" type="button" aria-label="Remove guest">×</button>`;label.querySelector('button').addEventListener('click',()=>{label.remove();guests-=1});container.append(label);if(guests>=3)booking.querySelector('[data-add-guest]').hidden=true});container.addEventListener('click',()=>{if(guests<3)booking.querySelector('[data-add-guest]').hidden=false})}

const dialog=document.querySelector('[data-lightbox-dialog]');
if(dialog){document.querySelectorAll('[data-lightbox]').forEach(button=>button.addEventListener('click',()=>{dialog.querySelector('img').src=button.dataset.lightbox;dialog.showModal()}));dialog.querySelector('[data-lightbox-close]').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()})}

window.setTimeout(()=>document.querySelectorAll('.flash').forEach(el=>el.remove()),5000);
