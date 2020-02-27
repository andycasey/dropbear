(() => {
  $(function () {

    // Enable popovers
    $('[data-toggle="popover"]').popover();

    //
    let timeout = null;
    let authors = {};
    const template = document.getElementById("rowTemplate").innerHTML;
    let table = document.getElementById("resultsTable");
    function updateTable() {
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => {
        let rows = "";
        for (const name in authors) {
          rows += Mustache.render(template, authors[name]);
        }
        document.getElementById("tableBody").innerHTML = rows;
        Sortable.initTable(table);
      }, 1000);
    }

    // Enable search
    const field = document.getElementById("authorName");
    document.getElementById("searchForm").onsubmit = (event) => {
      event.preventDefault();
      authors = {};
      const name = field.value;
      if (!name) return false;
      fetch("/search", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: name })
      })
        .then(async response => {
          const reader = response.body.getReader();
          let prevText = "";
          function process() {
            reader.read().then(({ value, done }) => {
              if (done) {
                return;
              }
              const text = prevText + new TextDecoder().decode(value);
              prevText = "";
              text.match(/[^\r\n]+/g).forEach((value) => {
                try {
                  const author = JSON.parse(value);
                  if (author.inferred_gender) {
                    if (author.inferred_gender == "andy") {
                      author.inferred_gender = "unknown";
                    } else if (author.inferred_gender.startsWith("mostly_")) {
                      author.inferred_gender = author.inferred_gender.substring(7);
                    }
                  }
                  authors[author.unique_name_descriptor] = author;
                }
                catch (err) {
                  prevText = value;
                }
              });
              updateTable();
              process();
            });
          }
          process();
        });
      return false;
    };

  });
})();
