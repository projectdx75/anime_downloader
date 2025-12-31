function global_sub_request_search(page, move_top=true) {
  var formData = get_formdata('#form_search')
  formData += '&page=' + page;
  $.ajax({
    url: '/' + package_name + '/ajax/' + sub + '/web_list',
    type: "POST",
    cache: false,
    data: formData,
    dataType: "json",
    success: function (data) {
      current_data = data;
      if (move_top)
        window.scrollTo(0,0);
      make_list(data.list)
      make_page_html(data.paging)
    }
  });
}

function get_formdata(form_id) {
  // on, off 일수도 있으니 모두 True, False로 통일하고
  // 밑에서는 False인 경우 값이 추가되지 않으니.. 수동으로 넣어줌
  var checkboxs = $(form_id + ' input[type=checkbox]');
  //for (var i in checkboxs) {
  for (var i =0 ; i < checkboxs.length; i++) {
    if ( $(checkboxs[i]).is(':checked') ) {
      $(checkboxs[i]).val('True');
    } else {
      $(checkboxs[i]).val('False');
    }
  }
  var formData = $(form_id).serialize();
  $.each($(form_id + ' input[type=checkbox]')
    .filter(function(idx) {
      return $(this).prop('checked') === false
    }),
    function(idx, el) {
      var emptyVal = "False";
      formData += '&' + $(el).attr('name') + '=' + emptyVal;
    }
  );
  formData = formData.replace("&global_scheduler=True", "")
  formData = formData.replace("&global_scheduler=False", "")
  formData = formData.replace("global_scheduler=True&", "")
  formData = formData.replace("global_scheduler=False&", "")
  return formData;
}

function globalRequestSearch2(page, move_top = true) {
  var formData = get_formdata("#form_search")
  formData += "&page=" + page
  console.log(formData)
  $.ajax({
    url: "/" + PACKAGE_NAME + "/ajax/" + MODULE_NAME + "/web_list2",
    type: "POST",
    cache: false,
    data: formData,
    dataType: "json",
    success: function (data) {
      current_data = data
      if (move_top) window.scrollTo(0, 0)
      make_list(data.list)
      make_page_html(data.paging)
    },
  })
}