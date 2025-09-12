// Variables
const baseHardLimit = 36;
const baseSoftLimit = 35;
let hardLimit = baseHardLimit;
let softLimit = baseSoftLimit;
let itemLimit = 2;


// Function to reset limits to base values
function resetLimits() {
    hardLimit = baseHardLimit;
    softLimit = baseSoftLimit;
}

// 1) To perform AJAX request upon NRIC query button press
async function nricQuery(event) {
    if (event) {
        event.preventDefault();
    }

    resetLimits();

    try {
        const form = document.getElementById('nric-form');
        const formData = new FormData(form);

        const response = await fetch('/query', {
            method: 'POST',
            body: new URLSearchParams(formData),
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
        });

        const data = await response.json();

        // Eligible to redeem
        if (data.type === 'N' || data.type === 'NR') {
            if (data.age >= 60) {
                hardLimit += 10;
                softLimit += 10;
            }

            document.getElementById("checkout-button").disabled = false;
            document.querySelector(".product-container").style.border = '5px solid #4CAF50';
            document.querySelector(".form-container").style.border = 'none';
            document.querySelector("#client-name").innerText =
                `Client: ${data.name}\n Available Credit: ${softLimit} tokens`;

            updateStatusText(`Client found: ${data.message}`, 'success');

        } 
        // Redeemed this month
        else if (data.type === 'R') {
            updateStatusText(data.message, 'error');
            const confirmed = confirm(`Already redeemed: ${data.message}, cancel transaction?`);
            if (confirmed) {
                location.reload(true);
            }    else {
                document.getElementById("checkout-button").disabled = false;
                document.querySelector(".product-container").style.border = '5px solid #4CAF50';
                document.querySelector(".form-container").style.border = 'none';
                document.querySelector("#client-name").innerText =
                    `Client: ${data.name}\n Available Credit: ${softLimit} tokens`;
            }
            // You can add more custom logic for 'R' here
        } 
        // New or not found
        else if (data.type === 'NF') {
            updateStatusText(data.message, 'error');
            // You can add more custom logic for 'NF' here
        }

    } catch (error) {
        console.error("Error querying NRIC:", error);
        updateStatusText("An error occurred while processing the request.", "error");
    }

    loadPopup();
    return false; // Prevent default form submission
}



// 2) Function to update status text
function updateStatusText(message, className) {
    const statusTextElement = document.querySelector("#status-text");
    if (statusTextElement) {
        statusTextElement.className = `status-text ${className}`;
        statusTextElement.innerText = message;
    }
}


// 2) Enables quantity selectors, validates 0-2, calls updateTotal() 
document.addEventListener('DOMContentLoaded', () => {
    const productCards = document.querySelectorAll('.product-card');

    // Define custom limits and unlimited products
    const customLimitedProducts = {
        'Eggs': 1,      // limit quantity to 1
    };
    const unlimitedProducts = ['Adult Milk Powder', 'Light Soya Sauce', 'Pepper', 'Canned Baked Beans']; // no limit

    productCards.forEach(card => {
        const quantityElement = card.querySelector('.product-quantity');
        const decreaseButton = card.querySelector('.quantity-decrease');
        const increaseButton = card.querySelector('.quantity-increase');
        const price = parseFloat(card.querySelector('.product-price').textContent.replace('$', ''));

        let quantity = parseInt(quantityElement.textContent, 10);
        const productName = card.querySelector('.product-name').textContent.trim();

        decreaseButton.addEventListener('click', () => {
            if (quantity > 0) {
                quantity--;
                quantityElement.textContent = quantity;
                updateTotal();
                updateCart();
                cardBorder();
            }
        });

        increaseButton.addEventListener('click', () => {
            // Unlimited products
            if (unlimitedProducts.includes(productName)) {
                quantity++;
            }
            // Custom limit products
            else if (customLimitedProducts[productName]) {
                if (quantity < customLimitedProducts[productName]) {
                    quantity++;
                }
            }
            // Default limit for other products
            else if (quantity < itemLimit) {
                quantity++;
            }

            quantityElement.textContent = quantity;
            updateTotal();
            updateCart();
            cardBorder();
        });

        // Reset quantity on query button click
        document.getElementById('query-btn').addEventListener('click', () => {
            quantity = 0;
            quantityElement.textContent = quantity;
        });
    });
});



function cardBorder() {
    const productCards = document.querySelectorAll('.product-card');
    productCards.forEach(card => {
        const quantityElement = card.querySelector('.product-quantity');
        const quantity = parseInt(quantityElement.textContent, 10);
        
        if (quantity !== 0) {
            card.style.border = '2px solid green';
        } else {
            card.style.border = ''; // Reset border if quantity is 0
        }
    });
}


// 3) Updates the total counter based on quantity*price, counter color to red if > soft limit
function updateTotal() {
    let total = 0;
    const productCards = document.querySelectorAll('.product-card');

    productCards.forEach(card => {
        const quantity = parseInt(card.querySelector('.product-quantity').textContent, 10);
        const price = parseFloat(card.querySelector('.product-price').textContent.replace(' tokens', ''));
        total += quantity * price;
    });

    const totalCounter = document.querySelector('#total-counter');
    totalCounter.innerText = `Total: ${total.toFixed(0)} tokens`;

    if (total > softLimit) {
        totalCounter.style.backgroundColor = 'red';
    } else {
        totalCounter.style.backgroundColor = ''; // Reset to default if total is not greater than spending limit
    }
}

// 4) Updates the shopping cart based on what was selected
function updateCart() {
    let transactionData = []; // Initialize transaction data array

    const productCards = document.querySelectorAll('.product-card');
    productCards.forEach(card => {
        const quantity = parseInt(card.querySelector('.product-quantity').textContent, 10);
        const price = parseFloat(card.querySelector('.product-price').textContent.replace(' tokens', ''));
        const item = card.querySelector('.product-name').textContent;
        const total = quantity * price;

        if (quantity > 0) {
            transactionData.push({
                "Item Name": item,
                "Item Quantity": quantity,
                "Item Price": price,
                "Total": total
            });
        }
    });
    const transactionLog = document.getElementById('transaction-log');
    transactionLog.innerHTML = ''; // Clear previous log

    transactionData.forEach(entry => {
        const logEntry = document.createElement('div');
        logEntry.className = 'transaction-entry';

        const itemName = document.createElement('span');
        itemName.className = 'item-name';
        itemName.textContent = `${entry["Item Name"]}`;

        const itemPrice = document.createElement('span');
        itemPrice.className = 'item-price';
        itemPrice.textContent = `${entry["Item Price"]} token/unit`;

        const itemQuantity = document.createElement('span');
        itemQuantity.className = 'item-quantity';
        itemQuantity.textContent = `Qty: ${entry["Item Quantity"]}`;
        
        const itemTotal=document.createElement('span');
        itemTotal.className = 'item-total'
        itemTotal.textContent = `Total: ${entry["Total"]} tokens`;

        logEntry.appendChild(itemName);
        logEntry.appendChild(itemPrice);
        logEntry.appendChild(itemQuantity);
        logEntry.appendChild(itemTotal);

        transactionLog.appendChild(logEntry);
    });
} 

function clearCart() {
    const productCards = document.querySelectorAll('.product-card');
    productCards.forEach(card => {
        const quantityElement = card.querySelector('.product-quantity');
        quantityElement.textContent = '0'; // Set the quantity to 0
    });
    updateCart();
    updateTotal();
    document.querySelector("#client-name").innerText = ``;
}

// Processes the transaction submission. Sends transaction details to server.
function checkOut() {
    const total = parseFloat(document.querySelector('#total-counter').textContent.replace('Total: ', '').replace(' tokens', ''));
    console.log(total)
    if (total > hardLimit) {
        alert(`Transaction blocked: Total price exceeds the limit of $${softLimit}. Please remove some items.`);
    } else {

    const userConfirmed = confirm(`Confirm Transaction? Client may purchase an additional ${softLimit-total} tokens worth of items.`);
    
    if (userConfirmed) {
        const productCards = document.querySelectorAll('.product-card');
        let checkoutList = [];

        // transaction details
        productCards.forEach(card => {
            const quantity = parseInt(card.querySelector('.product-quantity').textContent, 10);
            const price = parseFloat(card.querySelector('.product-price').textContent.replace(' tokens', ''));
            const item = card.querySelector('.product-name').textContent
            const itemtotal = quantity * price;

            if(quantity >0) {
                checkoutList.push({
                    ItemName: item, 
                    ItemQuantity:quantity, 
                    TotalPrice: itemtotal,
                    TotalSpent: total})
            }
        });

        const data = checkoutList
        const clientname = document.querySelector("#client-name").innerText

        console.log("Data to be sent:", data); // Debugging log

        // Sends the data (checkoutList) to server
        if (data && data.length > 0) {
            fetch('/check_out', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ data }),
            })
            .then(response => response.json())
            .then(data => {
                console.log(data.message);
                document.getElementById("checkout-button").disabled = true;
                document.querySelector(".product-container").style.border = '';
                document.querySelector(".form-container").style.border = '';
                document.getElementById('nric-input').value = '';
                alert(`Transaction successfully processed. Input another NRIC to conduct new transaction.`);
                location.reload(true)
                // document.getElementById('nric-input').focus();
                // clearCart();
                // cardBorder();
                // updateStatusText(`Please input new client NRIC.`, 'error');
            })
            .catch(error => {
                console.error('Error processing check-out:', error);
            });
        } else {
            console.log("Transaction was cancelled by the user.");
        }

    } else {
        console.log("Transaction was cancelled by the user.");
    }
}}    

function downloadTransactions() {
    fetch('/download_csv')
    .then(response => response.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'transactions.csv';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
    })
    .catch(error => console.error('Error downloading the CSV:', error));
}

function downloadInventory() {
    fetch('/download_inventory')
    .then(response => response.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'products.csv';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
    })
    .catch(error => console.error('Error downloading the CSV:', error));
}

$(document).ready(function() {
    function fetchTransaction(type, id) {
        $.get('/fetch', { type: type, id: id}, function(data) {
            let id = parseFloat(document.querySelector('#transaction-id').textContent.replace('Transaction ID: ', ''));
            console.log('Data received:', data); // Log the received data
            if (data && data.details && Array.isArray(data.details)) {
                var tbody = $('#transaction-table tbody');
                tbody.empty();
                data.details.forEach(function(detail) {
                    var row = $('<tr></tr>');
                    row.append($('<td></td>').text(detail.item));
                    row.append($('<td></td>').text(detail.quantity));
                    tbody.append(row);
                });
                $('#transaction-client').text('Client Name: ' + data.client_name); // Set the transaction Name
                $('#transaction-date').text('Transaction Date: ' + data.transaction_date); // Set the transaction date
                $('#transaction-id').text('Transaction ID: ' + data.transaction_id); // Set the transaction ID
                $('#transaction-table').show();
                document.getElementById("next").disabled = false;
                document.getElementById("previous").disabled = false;
            } else {
                console.error('Invalid data format:', data);
            }
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.error('Error fetching data:', textStatus, errorThrown);
        });
    }

    $('#latest').click(function() {
        let id = parseFloat(document.querySelector('#transaction-id').textContent.replace('Transaction ID: ', ''));
        fetchTransaction('latest', id);
    });

    $('#previous').click(function() {
        let id = parseFloat(document.querySelector('#transaction-id').textContent.replace('Transaction ID: ', ''));
        fetchTransaction('previous' , id);
    });

    $('#next').click(function() {
        fetchTransaction('next');
        let id = parseFloat(document.querySelector('#transaction-id').textContent.replace('Transaction ID: ', ''));
        fetchTransaction('next' , id);
    });
});

$(document).ready(function() {
    $('#sidebarToggle').click(function() {
        $('#sidebar').toggleClass('show');
    });
});



// Processes the transaction submission. Sends transaction details to server.
function submitStock() {
    const movementType = document.querySelector('#movement-type').value; // Get movement type
    const tableRows = document.querySelectorAll('.inventory-table tbody tr'); // Ensure correct selector
    const movementList = [];

    // Add movementType to the list once
    movementList.push({ MovementType: movementType });

    // Process transaction details
    tableRows.forEach((card, index) => {
        const productID = card.querySelector('.product-id') ? card.querySelector('.product-id').textContent.trim() : null;
        const movementQuantity = parseInt(card.querySelector('.movement-quantity').value, 10); // Use .value for input
        const movementSource = card.querySelector('.movement-source') ? card.querySelector('.movement-source').value : null;
        const movementRemarks = card.querySelector('.movement-remarks') ? card.querySelector('.movement-remarks').value : '';

        // Debugging logs
        console.log(`Row ${index}: Product ID: ${productID}, Quantity: ${movementQuantity}, Source: ${movementSource}, Remarks: ${movementRemarks}`);

        if (!isNaN(movementQuantity) && movementQuantity > 0) {
            movementList.push({
                productID: productID,
                movementQuantity: movementQuantity,
                movementSource: movementSource,
                movementRemarks: movementRemarks
            });
        } else {
            console.log(`Row ${index} skipped due to invalid or zero quantity`);
        }
    });

    console.log("Data to be sent:", movementList); // Debugging log

    // Sends the data (movementList) to server
    fetch('/update_stock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ movementList }),
    })
    .then(async response => {
        const data = await response.json();  // parse JSON first
        if (!response.ok) {
            alert(data.message || 'Stock Update Error: Please contact administrator.');
            throw new Error(data.message || 'Network response was not ok');
        }
        return data;
    })
    .then(data => {
        alert(data.message);
        location.reload(true);
    })
    .catch(error => {
        // error already alerted above, just log here
        console.error('Fetch error:', error);
    });

}

//Triggers alert upon refresh attempt on pages with class warn-on-unload
document.addEventListener("DOMContentLoaded", function() {
    if (document.body.classList.contains('warn-on-unload')) {
        window.onbeforeunload = function() {
            return "Data will be lost if you leave the page, are you sure?";
        };
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const rowsPerPage = 25;
    const table = document.getElementById('inventory-table');
    const tbody = table.querySelector('tbody');
    const allRows = Array.from(tbody.querySelectorAll('tr'));
    const paginationControls = document.getElementById('pagination-controls');
    let currentPage = 1;
    let filteredRows = [...allRows];

    function displayRows(page) {
        const start = (page - 1) * rowsPerPage;
        const end = start + rowsPerPage;
        filteredRows.forEach((row, index) => {
            row.style.display = index >= start && index < end ? '' : 'none';
        });
    }

    function setupPagination() {
        const pageCount = Math.ceil(filteredRows.length / rowsPerPage);
        paginationControls.innerHTML = '';

        for (let i = 1; i <= pageCount; i++) {
            const button = document.createElement('button');
            button.textContent = i;
            button.classList.add('btn', 'btn-secondary', 'mx-1');
            if (i === currentPage) button.classList.add('active');
            button.addEventListener('click', () => {
                currentPage = i;
                displayRows(currentPage);
                document.querySelectorAll('#pagination-controls button').forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');
            });
            paginationControls.appendChild(button);
        }
    }

    displayRows(currentPage);
    setupPagination();
});


// inventory search function
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-product');
    const tableRows = document.querySelectorAll('#inventory-table tbody tr');

    searchInput.addEventListener('input', function() {
        const searchValue = this.value.toLowerCase().trim();

        tableRows.forEach(row => {
            const productName = row.children[1].textContent.toLowerCase(); // Name
            const brand = row.children[2].textContent.toLowerCase();       // Brand
            const typeInput = row.querySelector('.stock-type');            // Hidden input
            const type = typeInput ? typeInput.value.toLowerCase() : '';

            if (productName.includes(searchValue) || brand.includes(searchValue) || type.includes(searchValue)) {
                row.style.display = ''; // show row
            } else {
                row.style.display = 'none'; // hide row
            }
        });
    });
});



    // Add event listener for form submission
async function submitForm(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const response = await fetch('/add_client', {
    method: 'POST',
    body: formData
    });

    const result = await response.json();
    alert(result.message);
    if (response.ok) {
    event.target.reset();
    }
}
