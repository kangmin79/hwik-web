
(function(){
  var p = new URLSearchParams(location.search);
  var id = p.get('id');
  if (!id) { location.replace('/'); return; }
  try {
    var sb = supabase.createClient(HWIK_CONFIG.SUPABASE_URL, HWIK_CONFIG.SUPABASE_KEY);
    sb.from('danji_pages')
      .select('id,complex_name,location,address')
      .eq('id', id)
      .limit(1)
      .then(function(r){
        var row = r && r.data && r.data[0];
        if (!row) { location.replace('/'); return; }
        var slug = makeSlug(row.complex_name, row.location, row.id, row.address || '');
        if (!slug) { location.replace('/'); return; }
        location.replace('/danji/' + slug);
      })
      .catch(function(){ location.replace('/'); });
  } catch(e) { location.replace('/'); }
})();
