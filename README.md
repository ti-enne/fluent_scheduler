# Fluent Scheduler

Simulation scheduler and automation toolkit for **ANSYS Fluent**, designed to simplify the execution, monitoring and management of CFD simulations.

The project extends the standard Fluent workflow with additional automation features, allowing engineers to organize simulation runs, launch jobs through a graphical interface and streamline repetitive CFD activities.

---

## Features

- Schedule ANSYS Fluent simulation executions
- Automate repetitive simulation workflows
- Graphical User Interface (GUI) based on **Tkinter**
- Modular architecture for future extensions
- Utility scripts for simulation process management
- Simplified handling of multiple simulation runs

---

## Requirements

- Python 3.x
- ANSYS Fluent
- Windows environment (batch launchers are included)
- Required Python dependencies

Example:

```bash
pip install -r requirements.txt
```

---

## Running the Application

### GUI Mode

```bash
python main_tkinter.py
```

or simply execute:

```cmd
main_tkinter.bat
```

### Command Line Mode

```bash
python main.py
```

---

## Typical Workflow

1. Configure the Fluent simulation.
2. Define scheduling or execution parameters.
3. Launch the scheduler.
4. Monitor simulation progress.
5. Automatically manage and organize multiple runs.

---

## Use Cases

- Night-time batch execution of CFD simulations
- Sequential execution of multiple Fluent cases
- Management of long-running analyses
- Reduction of manual intervention during simulation campaigns
- Engineering automation workflows

---

## Architecture

The project follows a modular structure:

- **Launcher Layer**
  - Application startup scripts
- **GUI Layer**
  - Tkinter-based user interface
- **Scheduler Layer**
  - Simulation execution logic
- **Utility Layer**
  - Process and Fluent-management tools

This design simplifies maintenance and future feature development.

---

## Future Improvements

Potential extensions include:

- Queue management
- Email notifications
- Remote execution support
- Simulation status dashboard
- Log aggregation and reporting
- Multi-machine scheduling

---

## Author

Developed by **ti-enne**

Repository:

https://github.com/ti-enne/fluent_scheduler

---

## Disclaimer

This project is an unofficial automation tool for ANSYS Fluent and is not affiliated with Ansys Inc.
