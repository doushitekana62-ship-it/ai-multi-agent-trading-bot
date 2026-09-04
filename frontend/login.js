const $=s=>document.querySelector(s);let client;
async function init(){const cfg=await fetch('/config').then(r=>r.json());client=window.supabase.createClient(cfg.supabase_url,cfg.supabase_anon_key);const {data}=await client.auth.getSession();if(data.session)location.href='/';}
$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();const {error}=await client.auth.signInWithPassword({email:$('#email').value.trim(),password:$('#password').value});if(error){$('#loginError').textContent=error.message;return}location.href='/';});
init();