def initialize_app() -> None:
    print("Initializing Limencore...")

#load configs
#prepare the database
#validate environment
#initialize services


def run_app() -> None:
    print("Limencore is running")


#Interface
#dashboard
#loop principal 
#API, arquitetura final(a decidir)



def main() -> None:
    try:
        initialize_app()
        run_app()
    except Exception as error:
        print(f"Failed to start Limencore: {error}")
        
        


if __name__ == "__main__":
    main()