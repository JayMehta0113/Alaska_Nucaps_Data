let elasped_seconds = 0
let start_time = null;

async function startProcessing() {

    elasped_seconds = 0;
    start_time = null;

    // Disable the button to prevent multiple clicks
    const startButton = document.getElementById("start-button");
    startButton.disabled = true;

     // Clear the results textbox
    const textbox = document.getElementById('results');
    textbox.value = ''; // Clear the textbox upon starting

    // Get form data
    const formData = new FormData(document.getElementById('query-form'));
    const data = Object.fromEntries(formData.entries());

    // Convert string inputs to numbers
    data.year = parseInt(data.year);
    data.month = parseInt(data.month);
    data.day = parseInt(data.day);

    data.lat_min = parseInt(data.lat_min)
    data.lat_max = parseInt(data.lat_max)
    data.long_min = parseInt(data.long_min)
    data.long_max = parseInt(data.long_max)


    try {
        // Start processing by sending a POST request
        const response = await fetch('/start_query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            pollProgress(); // Start polling for progress
        } else {
            const message = await response.json();
            alert(message.message); // Notify user that processing is already running
        }
    } catch (error) {
        console.error("Error starting processing:", error);
        alert("An error occurred while starting processing.");
    } finally {
        // Re-enable the button after handling the request
        startButton.disabled = false;
    }
}

async function pollProgress() {
    const processedFiles = new Set(); // Track unique files already displayed
    let last_processed_file_count = 0;
    elasped_seconds = 0;
    let isGeneratingMap = false;
    const interval = setInterval(async () => {
        try {
            const response = await fetch('/get_progress');
            const data = await response.json();

            console.log("progress is: " + data.progress.status)
            console.log("num files: " + data.progress.files_processed)
            console.log(data.progress)
            if (data.progress.bucket == "aerosol_depth") {
                const textbox = document.getElementById('results');
                textbox.value = data.results; 
            }

            if (data.progress.found_file === true){
                clearInterval(interval);
                alert("File Found")
                return;
            }

            // Stop polling if no files are found
            if (data.progress.status === "no_files") {
                clearInterval(interval);
                alert("No files found for the specified date. Please check your input.");
                return;
            }

            if (data.stop_requested === true) {
                clearInterval(pollingInterval);
                alert("Query stopped. Results are preserved.");
                return;
            }

            //calculating estimate time left
            if(!start_time){
                start_time = Date.now();
            }
            else{
                elasped_seconds = (Date.now() - start_time)/1000;
            }


            const current_mins = Math.floor(elasped_seconds/60);
            const current_secs = Math.floor(elasped_seconds%60);
            const elapsed_time_element = document.getElementById("time_spent")
            elapsed_time_element.innerText = `Elapsed time: ${current_mins}:${current_secs < 10 ? "0" : ""}${current_secs}`

            const total_files = data.progress.total_files;
            const files_processed = data.progress.files_processed;
            const files_left = total_files - files_processed;

            //displaying time left mafter showing files remaining
            if(elasped_seconds > 0 && files_processed >0){
                const avg_files_per_second = files_processed/elasped_seconds;
                const remaining_time = files_left / avg_files_per_second;
                const mins = Math.floor(remaining_time/60);
                const seconds = Math.floor(remaining_time % 60);

                const time_left_element = document.getElementById("time_left");
                time_left_element.innerText = `Estimated time remaining: ${mins}:${seconds < 10 ? "0" : ""}${seconds}`
            }

            if(data.progress.bucket == "cris_radiances"){
            // Update the results textbox with unique files
                var count = 0;
                const textbox = document.getElementById('results');
                data.results.forEach((file) => {
                    if (!processedFiles.has(file.file)) {
                        processedFiles.add(file.file);
                        textbox.value += `File: ${file.file}\n`;
                        textbox.value += `Lat Range: ${file.lat_min} to ${file.lat_max}, Lon Range: ${file.long_min} to ${file.long_max}\n\n`;
                    }
                    count++
                });
            }

            const counter = document.getElementById('counter');
            counter.innerText = `Files Left: ${files_left}.  Files in range: ${count}`;


            // Stop polling if processing is complete
            if (data.progress.status === "completed") {
                console.log("completed")
                clearInterval(interval);
                alert("Processing complete!");
                await generateMap();
                return;
            }

        } catch (error) {
            clearInterval(interval);
            console.error("Error polling progress:", error);
            alert("An error occurred while checking progress.");
        }
    }, 2000);
}

async function stopProcessing() {
    try {
        const response = await fetch('/stop_query', { method: 'POST' });

        if (response.ok) {
            const message = await response.json();
            alert(message.message); // Notify user that the query is stopping
        } else {
            alert("No query is currently running.");
        }
    } catch (error) {
        console.error("Error stopping query:", error);
        alert("An error occurred while stopping the query.");
    }
}

//downloading the files
async function downloadAllFilesAsZip() {

    const year = document.getElementById("year").value
    const month = document.getElementById("month").value
    const day = document.getElementById("day").value

    try {
        const response = await fetch('/download_all_files');

        if (!response.ok) {
            alert("Failed to download files as ZIP.");
            return;
        }

        // Create a blob from the response
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        // Create a link element and trigger the download
        const link = document.createElement("a");
        link.href = url;
        link.download = `NUCAPS-CCR_${year}-${month}-${day}.zip`; // Name for the ZIP file
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        console.error("Error downloading ZIP file:", error);
        alert("An error occurred while downloading the ZIP file.");
    }
}

async function generateMap() {
    const loadingElement = document.getElementById("loading");
    const mapViewer = document.getElementById("Map_USA");

    const formData = new FormData(document.getElementById('query-form'));
    const data = Object.fromEntries(formData.entries());

    // Convert string inputs to numbers
    data.lat_min = parseInt(data.lat_min)
    data.lat_max = parseInt(data.lat_max)
    data.long_min = parseInt(data.long_min)
    data.long_max = parseInt(data.long_max)

    try {
        // Show the loading GIF
        loadingElement.style.display = "block";

        // Fetch the map image from the backend
        const response = await fetch('/grid_and_render', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || "Failed to generate map.");
        }

        const blob = await response.blob();
        const objectURL = URL.createObjectURL(blob);

        // Update the map image
        mapViewer.src = objectURL;
    } catch (error) {
        console.error("Error generating map:", error);
        alert("Failed to generate map.");
    } finally {
        // Hide the loading GIF
        loadingElement.style.display = "none";
    }
}
