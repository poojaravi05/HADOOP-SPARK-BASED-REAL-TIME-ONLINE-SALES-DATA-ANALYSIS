from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import time

kafka_bootstrapServers = 'localhost:9092'
kafka_topic = "orderstopic"
customers_Filepath = "/home/hadoop/Downloads/customers.csv"



mysql_Hostname = "localhost"
mysql_Portno = "3306"
mysql_DBname = "sales_data"
mysql_Driverclass = "com.mysql.jdbc.Driver"
mysql_Table1 = "sales_orders_tbl"
mysql_Username = "meghana"
mysql_Password = "Meghana@123"
mysql_jdbc_url = "jdbc:mysql://" + mysql_Hostname + ":" + mysql_Portno + "/" + mysql_DBname

cassandra_host_name = "pooja-VirtualBox"
cassandra_port_no = "9042"
cassandra_keyspace_name = "sales_ks"
cassandra_table_name = "orders_tbl"

   # function to save raw data to cassandra database

def saveto_cassandraTable(current_df, epoc_id):

     current_df \
       .write \
       .format("org.apache.spark.sql.cassandra") \
       .mode("append") \
       .options(table=cassandra_table_name, keyspace=cassandra_keyspace_name) \
       .save()

   # function  to save processed data to mysql database

def saveto_mysqlTable(current_df, epoc_id):
    db_credentials = {"user": mysql_Username,
                      "password": mysql_Password,
                      "driver": mysql_Driverclass}

    processed_Time = time.strftime("%Y-%m-%d %H:%M:%S")

    current_df_final = current_df \
       .withColumn("processed_at", lit(processed_Time)) \
       .withColumn("batch_id", lit(epoc_id))

    current_df_final \
        .write \
        .jdbc(url=mysql_jdbc_url,
              table=mysql_Table1 ,
              mode="append",
              properties=db_credentials)



if __name__ == "__main__":
    print("Spark Data Processing of the Application Started......")
    print(time.strftime("%Y-%m-%d %H:%M:%S"))

    spark = SparkSession \
        .builder \
        .appName("Pyspark streaming with Kafka") \
        .master("local[*]") \
        .config("spark.jars",
                "file:///home/hadoop/jars/spark-sql-kafka-0-10_2.12-3.1.1.jar,file:///home/hadoop/jars/kafka-clients-1.1.0.jar,file:///home/hadoop/jars/spark-streaming-kafka-0-10-assembly_2.12-3.0.0-preview2.jar,file:///home/hadoop/jars/mysql-connector-java-8.0.26.jar,file:///home/hadoop/jars/commons-pool2-2.6.2.jar,file:///home/hadoop/jars/spark-token-provider-kafka-0-10_2.12-3.0.1.jar") \
        .config("spark.executor.extraClassPath",
                "file:///home/hadoop/jars/spark-sql-kafka-0-10_2.12-3.1.1.jar:file:///home/hadoop/jars/kafka-clients-1.1.0.jar:file:///home/hadoop/jars/spark-streaming-kafka-0-10-assembly_2.12-3.0.0-preview2.jar:file:///home/hadoop/jars/mysql-connector-java-8.0.26.jar:file:///home/hadoop/jars/commons-pool2-2.6.2.jar:file:///home/hadoop/jars/spark-token-provider-kafka-0-10_2.12-3.0.1.jar") \
        .config("spark.executor.extraLibrary",
                "file:///home/hadoop/jars/spark-sql-kafka-0-10_2.12-3.1.1.jar:file:///home/hadoop/jars/kafka-clients-1.1.0.jar:file:///home/hadoop/jars/spark-streaming-kafka-0-10-assembly_2.12-3.0.0-preview2.jar:file:///home/hadoop/jars/mysql-connector-java-8.0.26.jar:file:///home/hadoop/jars/commons-pool2-2.6.2.jar:file:///home/hadoop/jars/spark-token-provider-kafka-0-10_2.12-3.0.1.jar") \
        .config("spark.driver.extraClassPath",
                "file:///home/hadoop/jars/spark-sql-kafka-0-10_2.12-3.1.1.jar:file:///home/hadoop/jars/kafka-clients-1.1.0.jar:file:///home/hadoop/jars/spark-streaming-kafka-0-10-assembly_2.12-3.0.0-preview2.jar:file:///home/hadoop/jars/mysql-connector-java-8.0.26.jar:file:///home/hadoop/jars/commons-pool2-2.6.2.jar:file:///home/hadoop/jars/spark-token-provider-kafka-0-10_2.12-3.0.1.jar") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("ERROR")

    # constructing a streaming dataframe that reads from kafka consumer produced

    orders_df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_bootstrapServers) \
        .option("subscribe", kafka_topic) \
        .option("startingOffsets", "earliest") \
        .load()

    print("Printing Schema of orders_df: ")
    orders_df.printSchema()

    ordersCasted_df = orders_df.selectExpr("CAST(value AS STRING)", "timestamp")

    # Define a schema for orders data

    orders_schema = StructType() \
        .add("order_id", StringType()) \
        .add("created_at", StringType()) \
        .add("discount", StringType()) \
        .add("product_id", StringType()) \
        .add("quantity", StringType()) \
        .add("subtotal", StringType()) \
        .add("tax", StringType()) \
        .add("total", StringType()) \
        .add("customer_id", StringType())
    orders_df2 = ordersCasted_df \
        .select(from_json(col("value"), orders_schema).alias("orders"), "timestamp")

    orders_df3 = orders_df2.select("orders.*", "timestamp")

    orders_df3 \
        .writeStream \
        .trigger(processingTime='15 seconds') \
        .outputMode("update") \
        .foreachBatch(saveto_cassandraTable) \
        .start()

    customers_Dataframe = spark.read.csv(customers_Filepath, header=True, inferSchema=True)
    customers_Dataframe.printSchema()
    customers_Dataframe.show(5, False)

    orders_df4 = orders_df3.join(customers_Dataframe, orders_df3.customer_id == customers_Dataframe.ID, how='inner')
    print("Printing Schema of Order_df4: ")
    orders_df4.printSchema()

    # Simple Aggregate - find total_sum_amount by grouping source , state

    orders_df5 = orders_df4.groupBy("Source", "State") \
        .agg({'total': 'sum'}).select("Source", "State", col("sum(total)").alias("Amount_Paid"))
    print("Printing Schema of orders_df5: ")
    orders_df5.printSchema()

    # Write Final Result into console for debugging purpose
    transDetail_WriteStream = orders_df5 \
        .writeStream \
        .trigger(processingTime='15 seconds') \
        .outputMode("update") \
        .option("truncate", "false") \
        .format("console") \
        .start()

    orders_df5 \
        .writeStream \
        .trigger(processingTime='15 seconds') \
        .outputMode("update") \
        .foreachBatch(saveto_mysqlTable) \
        .start()
    transDetail_WriteStream.awaitTermination()
