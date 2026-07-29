$(document).ready(function() {
    let products = [
        { sku: 'PROD-001', name: 'Laptop Pro 15', category: 'Electrónica', price: 1200.00, stock: 10, critical: 5 },
        { sku: 'PROD-002', name: 'Silla Ergonómica', category: 'Mobiliario', price: 150.00, stock: 2, critical: 3 }
    ];

    const productModal = new bootstrap.Modal(document.getElementById('productModal'));
    const deleteModal = new bootstrap.Modal(document.getElementById('deleteModal'));
    const inventoryModal = new bootstrap.Modal(document.getElementById('inventoryModal'));

    function renderTable() {
        const tbody = $('#productsTable tbody');
        tbody.empty();
        
        if (products.length === 0) {
            tbody.append(`<tr><td colspan="4" class="text-center text-muted py-4">No hay productos registrados.</td></tr>`);
            return;
        }

        products.forEach((prod, index) => {
            tbody.append(`
                <tr>
                    <td class="fw-bold">${prod.sku}</td>
                    <td>${prod.name}</td>
                    <td><span class="badge bg-primary">${prod.category}</span></td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-outline-success me-2 btn-inventory" data-index="${index}">Inventario</button>
                        <button class="btn btn-sm btn-outline-info me-2 btn-edit" data-index="${index}">Editar</button>
                        <button class="btn btn-sm btn-outline-danger btn-delete" data-index="${index}">Eliminar</button>
                    </td>
                </tr>
            `);
        });
    }

    function renderInventoryTable() {
        const tbody = $('#inventoryTable tbody');
        tbody.empty();
        
        if (products.length === 0) {
            tbody.append(`<tr><td colspan="6" class="text-center text-muted py-4">No hay productos en inventario.</td></tr>`);
            return;
        }

        products.forEach((prod) => {
            const price = parseFloat(prod.price || 0).toFixed(2);
            const stock = parseInt(prod.stock || 0);
            const critical = parseInt(prod.critical || 0);
            
            let stockClass = '';
            if (stock <= critical) {
                stockClass = 'text-danger fw-bold';
            }

            tbody.append(`
                <tr>
                    <td class="fw-bold">${prod.sku}</td>
                    <td>${prod.name}</td>
                    <td><span class="badge bg-secondary">${prod.category}</span></td>
                    <td>$${price}</td>
                    <td class="${stockClass}">${stock}</td>
                    <td>${critical}</td>
                </tr>
            `);
        });
    }

    renderTable();
    renderInventoryTable();

    function resetFormErrors() {
        $('#prodSku, #prodName, #prodCat').removeClass('is-invalid');
    }

    $('#btnAddProduct').on('click', function() {
        $('#productModalLabel').text('Nuevo Producto');
        $('#productForm')[0].reset();
        $('#editIndex').val('-1');
        resetFormErrors();
        productModal.show();
    });

    $('#btnSaveProduct').on('click', function() {
        let isValid = true;
        const sku = $('#prodSku').val().trim();
        const name = $('#prodName').val().trim();
        const category = $('#prodCat').val().trim();
        const index = parseInt($('#editIndex').val());

        if (sku === '') {
            $('#prodSku').addClass('is-invalid');
            isValid = false;
        } else {
            $('#prodSku').removeClass('is-invalid');
        }

        if (name === '') {
            $('#prodName').addClass('is-invalid');
            isValid = false;
        } else {
            $('#prodName').removeClass('is-invalid');
        }

        if (category === '') {
            $('#prodCat').addClass('is-invalid');
            isValid = false;
        } else {
            $('#prodCat').removeClass('is-invalid');
        }

        if(!isValid) return;

        if (index === -1) {
            products.push({ sku, name, category, price: 0, stock: 0, critical: 0 });
        } else {
            // Keep existing inventory details if editing
            const curr = products[index];
            products[index] = { sku, name, category, price: curr.price, stock: curr.stock, critical: curr.critical };
        }

        productModal.hide();
        renderTable();
        renderInventoryTable();
    });

    $('#prodSku, #prodName, #prodCat').on('input', function() {
        if($(this).val().trim() !== '') {
            $(this).removeClass('is-invalid');
        }
    });

    $(document).on('click', '.btn-edit', function() {
        const index = $(this).data('index');
        const prod = products[index];

        $('#productModalLabel').text('Editar Producto');
        $('#editIndex').val(index);
        $('#prodSku').val(prod.sku);
        $('#prodName').val(prod.name);
        $('#prodCat').val(prod.category);
        
        resetFormErrors();
        productModal.show();
    });

    $(document).on('click', '.btn-delete', function() {
        const index = $(this).data('index');
        const prod = products[index];

        $('#deleteIndex').val(index);
        $('#deleteProductDetails').text(`${prod.sku} - ${prod.name}`);
        
        deleteModal.show();
    });

    $('#btnConfirmDelete').on('click', function() {
        const index = parseInt($('#deleteIndex').val());
        if (index >= 0) {
            products.splice(index, 1);
            deleteModal.hide();
            renderTable();
            renderInventoryTable();
        }
    });

    $(document).on('click', '.btn-inventory', function() {
        const index = $(this).data('index');
        const prod = products[index];

        $('#invIndex').val(index);
        $('#invProductDetails').text(`${prod.sku} - ${prod.name}`);
        $('#invPrice').val(prod.price || 0);
        $('#invStock').val(prod.stock || 0);
        $('#invCritical').val(prod.critical || 0);
        
        $('#invPrice, #invStock, #invCritical').removeClass('is-invalid');
        
        inventoryModal.show();
    });

    $('#btnSaveInventory').on('click', function() {
        let isValid = true;
        const index = parseInt($('#invIndex').val());
        const priceVal = parseFloat($('#invPrice').val());
        const stockVal = parseInt($('#invStock').val());
        const criticalVal = parseInt($('#invCritical').val());

        if (isNaN(priceVal) || priceVal <= 0) {
            $('#invPrice').addClass('is-invalid');
            isValid = false;
        } else {
            $('#invPrice').removeClass('is-invalid');
        }

        if (isNaN(stockVal) || stockVal < 0) {
            $('#invStock').addClass('is-invalid');
            isValid = false;
        } else {
            $('#invStock').removeClass('is-invalid');
        }

        if (isNaN(criticalVal) || criticalVal < 0) {
            $('#invCritical').addClass('is-invalid');
            isValid = false;
        } else {
            $('#invCritical').removeClass('is-invalid');
        }

        if (!isValid || index === -1) return;

        products[index].price = priceVal;
        products[index].stock = stockVal;
        products[index].critical = criticalVal;

        inventoryModal.hide();
        renderInventoryTable();
    });
});
